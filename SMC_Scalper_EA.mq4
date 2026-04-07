//+------------------------------------------------------------------+
//|                                              SMC_Scalper_EA.mq4  |
//|                         SMC Price Action Scalper - MT4            |
//|                     M15 Structure + M5 Entry (OB/FVG/Sweep)      |
//+------------------------------------------------------------------+
#property copyright "SMC Scalper EA"
#property link      ""
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| INPUTS                                                            |
//+------------------------------------------------------------------+
// --- Instrument Preset ---
input bool   UseNasdaqPreset    = false;   // Use Nasdaq (NAS100/USTEC) preset
input bool   UseGoldPreset      = false;   // Use Gold (XAUUSD) preset

// --- Risk Management ---
input double RiskPercent        = 1.0;     // Risk % per trade
input double MaxSpreadPips      = 3.0;     // Max spread allowed (pips)
input int    MagicNumber        = 20240407;// Magic number
input int    MaxOpenTrades      = 1;       // Max simultaneous trades
input double MinRR              = 2.5;     // Minimum Risk:Reward ratio
input double SL_BufferPips      = 5.0;     // SL buffer beyond OB (pips)
input double MinSL_Pips         = 10.0;    // Minimum SL distance (pips)

// --- Structure Detection (M15) ---
input int    StructureLookback  = 20;      // Bars to look back for swing H/L
input int    SwingStrength      = 2;       // Bars on each side for swing point
input bool   UseEMA_Bias        = true;    // Use EMA as fallback bias filter
input int    EMA_Period         = 50;      // EMA period for bias (M15)
input bool   UseHTF_Filter      = true;    // Filter entries against H1 EMA trend
input int    HTF_EMA_Period     = 50;      // H1 EMA period for trend filter

// --- Order Block Detection (M5) ---
input int    OB_Lookback        = 50;      // Bars to scan for OB
input double OB_MinBodyRatio    = 0.3;     // Min body/range ratio for impulse candle
input int    OB_MinImpulsePips  = 5;       // Min impulse move (pips)
input bool   RequireConfluence  = false;   // Require OB+FVG or OB+Sweep (false=OB alone OK)

// --- FVG Detection (M5) ---
input int    FVG_Lookback       = 30;      // Bars to scan for FVG
input double FVG_MinSizePips    = 1.5;     // Min FVG size (pips)

// --- Liquidity Sweep ---
input int    LiqSweep_Lookback  = 40;      // Bars to scan for liq levels
input double LiqSweep_MinPips   = 2.0;     // Min sweep beyond level (pips)

// --- Entry Quality ---
input int    OB_MaxAgeBars      = 80;      // Max OB age in M5 bars (0=no limit)
input bool   RequirePullback    = false;   // Price must retrace into OB (not gap in)

// --- Session Filter ---
input int    LondonStartHour    = 8;       // London session start (server time)
input int    LondonEndHour      = 13;      // London session end (covers overlap)
input int    NYStartHour        = 13;      // New York session start
input int    NYEndHour          = 17;      // New York session end

// --- Trade Management ---
input bool   UseBreakeven       = true;    // Move SL to BE after 1R
input bool   UseTrailingStop    = true;    // Trail stop after 1R
input double TrailingRMultiple  = 1.0;     // R-multiple to start trailing
input bool   UsePartialClose    = true;    // Close 50% at TP1
input double TP1_Percent        = 50.0;    // % to close at TP1

// --- News Filter ---
input bool   UseNewsFilter      = true;    // Enable news filter
input int    NewsMinutesBefore  = 15;      // Stop trading X min before news
input int    NewsMinutesAfter   = 15;      // Resume trading X min after news
input string NewsFile           = "news_calendar.csv"; // News file in MQL4/Files/

//+------------------------------------------------------------------+
//| ENUMS & STRUCTS                                                   |
//+------------------------------------------------------------------+
enum BIAS_DIRECTION {
   BIAS_NONE = 0,
   BIAS_BULLISH = 1,
   BIAS_BEARISH = -1
};

struct SwingPoint {
   double price;
   int    barIndex;
   bool   isHigh;
};

struct OrderBlock {
   double top;
   double bottom;
   int    barIndex;
   bool   isBullish;
   bool   isValid;
   datetime time;
};

struct FVGZone {
   double top;
   double bottom;
   bool   isBullish;
   bool   isValid;
   int    barIndex;
};

struct NewsEvent {
   datetime time;
   string   currency;
   string   impact;    // "HIGH", "MEDIUM"
   string   title;
};

//+------------------------------------------------------------------+
//| GLOBALS                                                           |
//+------------------------------------------------------------------+
BIAS_DIRECTION g_currentBias = BIAS_NONE;
SwingPoint g_lastSwingHigh;
SwingPoint g_lastSwingLow;
SwingPoint g_prevSwingHigh;
SwingPoint g_prevSwingLow;
OrderBlock g_activeOBs[];
FVGZone    g_activeFVGs[];
NewsEvent  g_newsEvents[];
datetime   g_lastBarTime = 0;
datetime   g_lastNewsLoad = 0;
double     g_pipValue;
int        g_digits;

// Track tickets that already had TP1 partial close
int        g_tp1Tickets[];
int        g_tp1Count = 0;

// Cooldown & daily loss tracking
datetime   g_lastTradeClose = 0;
int        g_prevTradeCount = 0;
int        g_dailySLCount = 0;
datetime   g_currentDay = 0;

// Runtime values (may be overridden by Nasdaq/Gold preset)
double     g_maxSpreadPips;
int        g_obMinImpulsePips;
double     g_fvgMinSizePips;
double     g_liqSweepMinPips;
int        g_obLookback;
int        g_structureLookback;
int        g_swingStrength;
double     g_slBufferPips;
double     g_minSLPips;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(g_digits == 3 || g_digits == 5)
      g_pipValue = Point * 10;
   else
      g_pipValue = Point;

   // Default runtime values from inputs
   g_maxSpreadPips     = MaxSpreadPips;
   g_obMinImpulsePips  = OB_MinImpulsePips;
   g_fvgMinSizePips    = FVG_MinSizePips;
   g_liqSweepMinPips   = LiqSweep_MinPips;
   g_obLookback        = OB_Lookback;
   g_structureLookback = StructureLookback;
   g_swingStrength     = SwingStrength;
   g_slBufferPips      = SL_BufferPips;
   g_minSLPips         = MinSL_Pips;

   // Nasdaq preset: wider spread, bigger impulse/FVG thresholds (points not pips)
   if(UseNasdaqPreset) {
      g_pipValue          = Point;
      g_maxSpreadPips     = 50.0;
      g_obMinImpulsePips  = 80;
      g_fvgMinSizePips    = 30.0;
      g_liqSweepMinPips   = 20.0;
      g_obLookback        = 40;
      g_structureLookback = 30;
      g_swingStrength     = 4;
      g_slBufferPips      = 30.0;   // 30 pts buffer for Nasdaq
      g_minSLPips         = 50.0;   // 50 pts min SL for Nasdaq
      Print(">>> Nasdaq preset ACTIVE");
   }

   // Gold preset: XAUUSD
   if(UseGoldPreset) {
      g_pipValue          = 0.01;
      g_maxSpreadPips     = 40.0;
      g_obMinImpulsePips  = 50;
      g_fvgMinSizePips    = 20.0;
      g_liqSweepMinPips   = 15.0;
      g_obLookback        = 40;
      g_structureLookback = 25;
      g_swingStrength     = 4;
      g_slBufferPips      = 30.0;   // 30 pips buffer for Gold
      g_minSLPips         = 40.0;   // 40 pips min SL for Gold
      Print(">>> Gold preset ACTIVE");
   }

   if(UseNasdaqPreset && UseGoldPreset) {
      Print("WARNING: Both Nasdaq and Gold presets are ON — Gold preset takes priority");
   }

   if(UseNewsFilter) LoadNewsCalendar();

   Print("SMC Scalper EA initialized | Symbol: ", Symbol(),
         " | Pip value: ", g_pipValue,
         " | Risk: ", RiskPercent, "%",
         " | Preset: ", UseNasdaqPreset ? "NASDAQ" : (UseGoldPreset ? "GOLD" : "FOREX"),
         " | News filter: ", UseNewsFilter ? "ON" : "OFF");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   Print("SMC Scalper EA removed. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick() {
   // --- Manage open trades on EVERY tick (TP1/trailing must react fast) ---
   ManageOpenTrades();

   // --- Reset daily SL counter on new day ---
   datetime today = TimeCurrent() - TimeCurrent() % 86400;
   if(today != g_currentDay) {
      g_dailySLCount = 0;
      g_currentDay = today;
   }

   // --- Detect trade close for cooldown + daily SL tracking ---
   int currentTradeCount = CountOpenTrades();
   if(currentTradeCount < g_prevTradeCount) {
      g_lastTradeClose = TimeCurrent();
      for(int i = OrdersHistoryTotal() - 1; i >= 0; i--) {
         if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
         if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
         if(OrderCloseTime() >= TimeCurrent() - 60) {
            if(OrderProfit() < 0) g_dailySLCount++;
            break;
         }
      }
   }
   g_prevTradeCount = currentTradeCount;

   // --- New bar check (M5) — everything below runs once per bar ---
   datetime currentBarTime = iTime(Symbol(), PERIOD_M5, 0);
   if(currentBarTime == g_lastBarTime) return;
   g_lastBarTime = currentBarTime;

   // --- Pre-checks ---
   if(!IsSessionActive()) {
      if(IsTesting()) PrintOnce("FILTER_SESSION", "Blocked by session filter | Hour=" + IntegerToString(TimeHour(TimeCurrent())));
      return;
   }
   if(SpreadTooWide()) {
      if(IsTesting()) PrintOnce("FILTER_SPREAD", "Blocked by spread filter | Spread=" + DoubleToString(MarketInfo(Symbol(), MODE_SPREAD) * Point / g_pipValue, 1));
      return;
   }
   if(UseNewsFilter && IsNewsTime()) {
      if(IsTesting()) PrintOnce("FILTER_NEWS", "Blocked by news filter at " + TimeToString(TimeCurrent()));
      return;
   }
   // Daily loss limit: max 2 SL per day
   if(g_dailySLCount >= 2) return;
   // Cooldown: wait 2 hours after last trade close
   if(g_lastTradeClose > 0 && TimeCurrent() - g_lastTradeClose < 120 * 60) return;
   if(CountOpenTrades() >= MaxOpenTrades) return;

   // Reload news file daily
   if(UseNewsFilter && TimeCurrent() - g_lastNewsLoad > 86400) LoadNewsCalendar();

   // --- Step 1: M15 Structure Analysis (BOS detection) ---
   AnalyzeStructure();
   if(IsTesting() && g_currentBias == BIAS_NONE) {
      PrintOnce("FILTER_BIAS", "No bias detected (BIAS_NONE) at " + TimeToString(TimeCurrent()));
   }

   // --- Step 2: M5 Order Block Detection ---
   DetectOrderBlocks();

   // --- Step 3: M5 FVG Detection ---
   DetectFVGs();

   // --- Step 4: Check for Liquidity Sweep ---
   bool liqSweepBull = DetectLiquiditySweep(true);
   bool liqSweepBear = DetectLiquiditySweep(false);

   // --- Step 5: Entry Logic ---
   CheckEntry(liqSweepBull, liqSweepBear);
}

//+------------------------------------------------------------------+
//| SESSION FILTER                                                    |
//+------------------------------------------------------------------+
bool IsSessionActive() {
   int hour = TimeHour(TimeCurrent());
   if(hour >= LondonStartHour && hour < LondonEndHour) return true;
   if(hour >= NYStartHour && hour < NYEndHour) return true;
   return false;
}

//+------------------------------------------------------------------+
//| DEBUG: Print a message only once per key (avoids log spam)        |
//+------------------------------------------------------------------+
datetime g_lastDebugDay = 0;
void PrintOnce(string key, string message) {
   datetime today = TimeCurrent() - TimeCurrent() % 86400;
   if(today == g_lastDebugDay) return;
   g_lastDebugDay = today;
   Print("[DEBUG] ", message);
}

//+------------------------------------------------------------------+
//| SPREAD CHECK                                                      |
//+------------------------------------------------------------------+
bool SpreadTooWide() {
   double spread = MarketInfo(Symbol(), MODE_SPREAD) * Point / g_pipValue;
   return (spread > g_maxSpreadPips);
}

//+------------------------------------------------------------------+
//| COUNT OPEN TRADES                                                 |
//+------------------------------------------------------------------+
int CountOpenTrades() {
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| M15 STRUCTURE ANALYSIS - BOS Detection                           |
//+------------------------------------------------------------------+
void AnalyzeStructure() {
   SwingPoint swingHighs[];
   SwingPoint swingLows[];

   FindSwingPoints(PERIOD_M15, g_structureLookback, g_swingStrength, swingHighs, swingLows);

   BIAS_DIRECTION swingBias = BIAS_NONE;

   if(ArraySize(swingHighs) >= 2 && ArraySize(swingLows) >= 2) {
      g_lastSwingHigh = swingHighs[0];
      g_prevSwingHigh = swingHighs[1];
      g_lastSwingLow  = swingLows[0];
      g_prevSwingLow  = swingLows[1];

      double currentClose = iClose(Symbol(), PERIOD_M15, 0);

      // Strong BOS: price breaks swing + structure confirms
      if(currentClose > g_lastSwingHigh.price &&
         g_lastSwingLow.price > g_prevSwingLow.price) {
         swingBias = BIAS_BULLISH;
      }
      else if(currentClose < g_lastSwingLow.price &&
              g_lastSwingHigh.price < g_prevSwingHigh.price) {
         swingBias = BIAS_BEARISH;
      }
      // HH + HL = bullish
      else if(g_lastSwingHigh.price > g_prevSwingHigh.price &&
              g_lastSwingLow.price > g_prevSwingLow.price) {
         swingBias = BIAS_BULLISH;
      }
      // LH + LL = bearish
      else if(g_lastSwingHigh.price < g_prevSwingHigh.price &&
              g_lastSwingLow.price < g_prevSwingLow.price) {
         swingBias = BIAS_BEARISH;
      }
      // Partial: only HL = lean bullish
      else if(g_lastSwingLow.price > g_prevSwingLow.price) {
         swingBias = BIAS_BULLISH;
      }
      // Partial: only LH = lean bearish
      else if(g_lastSwingHigh.price < g_prevSwingHigh.price) {
         swingBias = BIAS_BEARISH;
      }
   }

   // EMA fallback: if swings give no clear direction, use EMA slope
   if(swingBias == BIAS_NONE && UseEMA_Bias) {
      double ema0 = iMA(Symbol(), PERIOD_M15, EMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
      double ema1 = iMA(Symbol(), PERIOD_M15, EMA_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
      double currentClose = iClose(Symbol(), PERIOD_M15, 0);

      if(currentClose > ema0 && ema0 > ema1)
         swingBias = BIAS_BULLISH;
      else if(currentClose < ema0 && ema0 < ema1)
         swingBias = BIAS_BEARISH;
   }

   g_currentBias = swingBias;
}

//+------------------------------------------------------------------+
//| FIND SWING POINTS                                                 |
//+------------------------------------------------------------------+
void FindSwingPoints(int tf, int lookback, int strength,
                     SwingPoint &highs[], SwingPoint &lows[]) {
   ArrayResize(highs, 0);
   ArrayResize(lows, 0);

   for(int i = strength; i < lookback - strength; i++) {
      // Swing high
      bool isSwingHigh = true;
      double highPrice = iHigh(Symbol(), tf, i);
      for(int j = 1; j <= strength; j++) {
         if(iHigh(Symbol(), tf, i - j) >= highPrice ||
            iHigh(Symbol(), tf, i + j) >= highPrice) {
            isSwingHigh = false;
            break;
         }
      }
      if(isSwingHigh) {
         int size = ArraySize(highs);
         ArrayResize(highs, size + 1);
         highs[size].price = highPrice;
         highs[size].barIndex = i;
         highs[size].isHigh = true;
      }

      // Swing low
      bool isSwingLow = true;
      double lowPrice = iLow(Symbol(), tf, i);
      for(int j = 1; j <= strength; j++) {
         if(iLow(Symbol(), tf, i - j) <= lowPrice ||
            iLow(Symbol(), tf, i + j) <= lowPrice) {
            isSwingLow = false;
            break;
         }
      }
      if(isSwingLow) {
         int size = ArraySize(lows);
         ArrayResize(lows, size + 1);
         lows[size].price = lowPrice;
         lows[size].barIndex = i;
         lows[size].isHigh = false;
      }
   }
}

//+------------------------------------------------------------------+
//| M5 ORDER BLOCK DETECTION                                         |
//+------------------------------------------------------------------+
void DetectOrderBlocks() {
   ArrayResize(g_activeOBs, 0);

   for(int i = 2; i < g_obLookback; i++) {
      double open_i  = iOpen(Symbol(), PERIOD_M5, i);
      double close_i = iClose(Symbol(), PERIOD_M5, i);
      double high_i  = iHigh(Symbol(), PERIOD_M5, i);
      double low_i   = iLow(Symbol(), PERIOD_M5, i);

      double open_imp  = iOpen(Symbol(), PERIOD_M5, i - 1);
      double close_imp = iClose(Symbol(), PERIOD_M5, i - 1);
      double high_imp  = iHigh(Symbol(), PERIOD_M5, i - 1);
      double low_imp   = iLow(Symbol(), PERIOD_M5, i - 1);

      double impBody  = MathAbs(close_imp - open_imp);
      double impRange = high_imp - low_imp;
      if(impRange == 0) continue;

      double impMovePips = impRange / g_pipValue;

      if(impMovePips < g_obMinImpulsePips) continue;
      if(impBody / impRange < OB_MinBodyRatio) continue;

      // Bullish OB: bearish candle + strong bullish impulse breaking above
      if(close_i < open_i && close_imp > open_imp) {
         if(close_imp > high_i) {
            OrderBlock ob;
            ob.top = high_i;
            ob.bottom = low_i;
            ob.barIndex = i;
            ob.isBullish = true;
            ob.isValid = true;
            ob.time = iTime(Symbol(), PERIOD_M5, i);

            if(!IsOBMitigated(ob, i)) {
               int size = ArraySize(g_activeOBs);
               ArrayResize(g_activeOBs, size + 1);
               g_activeOBs[size] = ob;
            }
         }
      }

      // Bearish OB: bullish candle + strong bearish impulse breaking below
      if(close_i > open_i && close_imp < open_imp) {
         if(close_imp < low_i) {
            OrderBlock ob;
            ob.top = high_i;
            ob.bottom = low_i;
            ob.barIndex = i;
            ob.isBullish = false;
            ob.isValid = true;
            ob.time = iTime(Symbol(), PERIOD_M5, i);

            if(!IsOBMitigated(ob, i)) {
               int size = ArraySize(g_activeOBs);
               ArrayResize(g_activeOBs, size + 1);
               g_activeOBs[size] = ob;
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| CHECK IF ORDER BLOCK HAS BEEN MITIGATED                          |
//+------------------------------------------------------------------+
bool IsOBMitigated(OrderBlock &ob, int obBarIndex) {
   for(int i = obBarIndex - 2; i >= 1; i--) {
      if(ob.isBullish) {
         if(iClose(Symbol(), PERIOD_M5, i) < ob.bottom) return true;
      } else {
         if(iClose(Symbol(), PERIOD_M5, i) > ob.top) return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| M5 FAIR VALUE GAP DETECTION                                      |
//+------------------------------------------------------------------+
void DetectFVGs() {
   ArrayResize(g_activeFVGs, 0);

   for(int i = 2; i < FVG_Lookback; i++) {
      double high_prev = iHigh(Symbol(), PERIOD_M5, i);
      double low_prev  = iLow(Symbol(), PERIOD_M5, i);
      double high_next = iHigh(Symbol(), PERIOD_M5, i - 2);
      double low_next  = iLow(Symbol(), PERIOD_M5, i - 2);

      // Bullish FVG: gap up
      if(low_next > high_prev) {
         double gapSize = (low_next - high_prev) / g_pipValue;
         if(gapSize >= g_fvgMinSizePips) {
            if(!IsFVGFilled(high_prev, low_next, true, i - 2)) {
               FVGZone fvg;
               fvg.top = low_next;
               fvg.bottom = high_prev;
               fvg.isBullish = true;
               fvg.isValid = true;
               fvg.barIndex = i - 1;
               int size = ArraySize(g_activeFVGs);
               ArrayResize(g_activeFVGs, size + 1);
               g_activeFVGs[size] = fvg;
            }
         }
      }

      // Bearish FVG: gap down
      if(high_next < low_prev) {
         double gapSize = (low_prev - high_next) / g_pipValue;
         if(gapSize >= g_fvgMinSizePips) {
            if(!IsFVGFilled(high_next, low_prev, false, i - 2)) {
               FVGZone fvg;
               fvg.top = low_prev;
               fvg.bottom = high_next;
               fvg.isBullish = false;
               fvg.isValid = true;
               fvg.barIndex = i - 1;
               int size = ArraySize(g_activeFVGs);
               ArrayResize(g_activeFVGs, size + 1);
               g_activeFVGs[size] = fvg;
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| CHECK IF FVG HAS BEEN FILLED                                     |
//+------------------------------------------------------------------+
bool IsFVGFilled(double bottom, double top, bool isBullish, int fromBar) {
   for(int i = fromBar - 1; i >= 1; i--) {
      if(isBullish) {
         if(iLow(Symbol(), PERIOD_M5, i) <= bottom) return true;
      } else {
         if(iHigh(Symbol(), PERIOD_M5, i) >= top) return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| LIQUIDITY SWEEP DETECTION                                        |
//+------------------------------------------------------------------+
bool DetectLiquiditySweep(bool checkBullish) {
   double liqLevel = 0;
   int tolerance = 3;

   if(checkBullish) {
      // Sweep of lows = bullish signal
      for(int i = 5; i < LiqSweep_Lookback; i++) {
         double low_i = iLow(Symbol(), PERIOD_M5, i);
         for(int j = i + 1; j < LiqSweep_Lookback; j++) {
            double low_j = iLow(Symbol(), PERIOD_M5, j);
            if(MathAbs(low_i - low_j) / g_pipValue <= tolerance) {
               liqLevel = MathMin(low_i, low_j);
               break;
            }
         }
         if(liqLevel > 0) break;
      }

      if(liqLevel == 0) return false;

      for(int i = 1; i <= 3; i++) {
         double low_i   = iLow(Symbol(), PERIOD_M5, i);
         double close_i = iClose(Symbol(), PERIOD_M5, i);
         if(low_i < liqLevel - g_liqSweepMinPips * g_pipValue &&
            close_i > liqLevel) {
            return true;
         }
      }
   }
   else {
      // Sweep of highs = bearish signal
      for(int i = 5; i < LiqSweep_Lookback; i++) {
         double high_i = iHigh(Symbol(), PERIOD_M5, i);
         for(int j = i + 1; j < LiqSweep_Lookback; j++) {
            double high_j = iHigh(Symbol(), PERIOD_M5, j);
            if(MathAbs(high_i - high_j) / g_pipValue <= tolerance) {
               liqLevel = MathMax(high_i, high_j);
               break;
            }
         }
         if(liqLevel > 0) break;
      }

      if(liqLevel == 0) return false;

      for(int i = 1; i <= 3; i++) {
         double high_i  = iHigh(Symbol(), PERIOD_M5, i);
         double close_i = iClose(Symbol(), PERIOD_M5, i);
         if(high_i > liqLevel + g_liqSweepMinPips * g_pipValue &&
            close_i < liqLevel) {
            return true;
         }
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| ENTRY LOGIC - Confluence Check                                    |
//+------------------------------------------------------------------+
void CheckEntry(bool liqSweepBull, bool liqSweepBear) {
   if(g_currentBias == BIAS_NONE) return;

   double bid = MarketInfo(Symbol(), MODE_BID);
   double ask = MarketInfo(Symbol(), MODE_ASK);

   // H4 trend filter: block counter-trend entries
   if(UseHTF_Filter) {
      double h4Ema  = iMA(Symbol(), PERIOD_H1, HTF_EMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
      double h4Close = iClose(Symbol(), PERIOD_H1, 0);
      // Don't buy if H4 is below EMA (bearish trend)
      if(g_currentBias == BIAS_BULLISH && h4Close < h4Ema) return;
      // Don't sell if H4 is above EMA (bullish trend)
      if(g_currentBias == BIAS_BEARISH && h4Close > h4Ema) return;
   }

   // --- BULLISH ENTRY ---
   if(g_currentBias == BIAS_BULLISH) {
      for(int i = 0; i < ArraySize(g_activeOBs); i++) {
         if(!g_activeOBs[i].isBullish || !g_activeOBs[i].isValid) continue;

         // Skip stale OBs
         if(OB_MaxAgeBars > 0 && g_activeOBs[i].barIndex > OB_MaxAgeBars) continue;

         // Price in OB zone
         if(bid <= g_activeOBs[i].top && bid >= g_activeOBs[i].bottom) {
            // Pullback check: previous bar close was above OB (price came down into it)
            if(RequirePullback) {
               double prevClose = iClose(Symbol(), PERIOD_M5, 1);
               if(prevClose < g_activeOBs[i].top) continue;
            }

            bool hasFVG = HasFVGConfluence(g_activeOBs[i], true);
            bool hasConfluence = hasFVG || liqSweepBull;

            if(hasConfluence || !RequireConfluence) {
               double sl = g_activeOBs[i].bottom - g_slBufferPips * g_pipValue;
               double slDist = (ask - sl) / g_pipValue;
               if(slDist < g_minSLPips)
                  sl = ask - g_minSLPips * g_pipValue;
               double tp1 = 0, tp2 = 0;
               FindTPLevels(true, ask, sl, tp1, tp2);

               double rr = (tp2 - ask) / (ask - sl);
               if(rr >= MinRR) {
                  string label = "SMC Buy|OB";
                  if(hasFVG) label = label + "+FVG";
                  if(liqSweepBull) label = label + "+Sweep";
                  ExecuteTrade(OP_BUY, ask, sl, tp2, label);
                  g_activeOBs[i].isValid = false;
                  return;
               }
            }
         }
      }
   }

   // --- BEARISH ENTRY ---
   if(g_currentBias == BIAS_BEARISH) {
      for(int i = 0; i < ArraySize(g_activeOBs); i++) {
         if(g_activeOBs[i].isBullish || !g_activeOBs[i].isValid) continue;

         // Skip stale OBs
         if(OB_MaxAgeBars > 0 && g_activeOBs[i].barIndex > OB_MaxAgeBars) continue;

         if(ask >= g_activeOBs[i].bottom && ask <= g_activeOBs[i].top) {
            // Pullback check: previous bar close was below OB (price came up into it)
            if(RequirePullback) {
               double prevClose = iClose(Symbol(), PERIOD_M5, 1);
               if(prevClose > g_activeOBs[i].bottom) continue;
            }

            bool hasFVG = HasFVGConfluence(g_activeOBs[i], false);
            bool hasConfluence = hasFVG || liqSweepBear;

            if(hasConfluence || !RequireConfluence) {
               double sl = g_activeOBs[i].top + g_slBufferPips * g_pipValue;
               double slDist = (sl - bid) / g_pipValue;
               if(slDist < g_minSLPips)
                  sl = bid + g_minSLPips * g_pipValue;
               double tp1 = 0, tp2 = 0;
               FindTPLevels(false, bid, sl, tp1, tp2);

               double rr = (bid - tp2) / (sl - bid);
               if(rr >= MinRR) {
                  string label = "SMC Sell|OB";
                  if(hasFVG) label = label + "+FVG";
                  if(liqSweepBear) label = label + "+Sweep";
                  ExecuteTrade(OP_SELL, bid, sl, tp2, label);
                  g_activeOBs[i].isValid = false;
                  return;
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| CANDLE CONFIRMATION - Rejection pattern on last closed M5 bar    |
//+------------------------------------------------------------------+
bool HasCandleConfirmation(bool bullish) {
   double open1  = iOpen(Symbol(), PERIOD_M5, 1);
   double close1 = iClose(Symbol(), PERIOD_M5, 1);
   double high1  = iHigh(Symbol(), PERIOD_M5, 1);
   double low1   = iLow(Symbol(), PERIOD_M5, 1);
   double range1 = high1 - low1;
   if(range1 == 0) return false;

   double body1  = MathAbs(close1 - open1);
   double upperWick = high1 - MathMax(open1, close1);
   double lowerWick = MathMin(open1, close1) - low1;

   if(bullish) {
      // Pin bar: long lower wick
      if(lowerWick > range1 * 0.6 && body1 < range1 * 0.35) return true;
      // Bullish engulfing
      double open2 = iOpen(Symbol(), PERIOD_M5, 2);
      double close2 = iClose(Symbol(), PERIOD_M5, 2);
      if(close1 > open1 && close2 < open2 && close1 > open2 && open1 < close2) return true;
      // Bullish rejection: close up, lower wick > body
      if(close1 > open1 && lowerWick > body1 && upperWick < body1) return true;
      // Hammer: close near high
      if(close1 > open1 && (high1 - close1) < range1 * 0.15 && lowerWick > range1 * 0.4) return true;
   } else {
      // Pin bar: long upper wick
      if(upperWick > range1 * 0.6 && body1 < range1 * 0.35) return true;
      // Bearish engulfing
      double open2 = iOpen(Symbol(), PERIOD_M5, 2);
      double close2 = iClose(Symbol(), PERIOD_M5, 2);
      if(close1 < open1 && close2 > open2 && open1 > close2 && close1 < open2) return true;
      // Bearish rejection: close down, upper wick > body
      if(close1 < open1 && upperWick > body1 && lowerWick < body1) return true;
      // Shooting star: close near low
      if(close1 < open1 && (close1 - low1) < range1 * 0.15 && upperWick > range1 * 0.4) return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| CHECK FVG CONFLUENCE WITH ORDER BLOCK                            |
//+------------------------------------------------------------------+
bool HasFVGConfluence(OrderBlock &ob, bool bullish) {
   for(int i = 0; i < ArraySize(g_activeFVGs); i++) {
      if(g_activeFVGs[i].isBullish != bullish) continue;
      if(!g_activeFVGs[i].isValid) continue;

      double overlapTop = MathMin(ob.top, g_activeFVGs[i].top);
      double overlapBottom = MathMax(ob.bottom, g_activeFVGs[i].bottom);

      if(overlapTop > overlapBottom) return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| FIND TP LEVELS (Multi-target SMC)                                |
//| Priority: 1) Opposing OB  2) Unfilled FVG  3) Swing liquidity   |
//+------------------------------------------------------------------+
void FindTPLevels(bool forBuy, double entry, double sl,
                  double &tp1, double &tp2) {
   double slDist = MathAbs(entry - sl);
   tp1 = 0;
   tp2 = 0;

   double currentPrice = MarketInfo(Symbol(), forBuy ? MODE_ASK : MODE_BID);

   // --- Collect all potential targets ---
   double targets[];
   ArrayResize(targets, 0);

   // 1) Opposing unfilled FVGs as targets
   for(int i = 0; i < ArraySize(g_activeFVGs); i++) {
      if(!g_activeFVGs[i].isValid) continue;
      if(forBuy && !g_activeFVGs[i].isBullish) {
         // Bearish FVG above = resistance target
         double mid = (g_activeFVGs[i].top + g_activeFVGs[i].bottom) / 2.0;
         if(mid > currentPrice) {
            int sz = ArraySize(targets);
            ArrayResize(targets, sz + 1);
            targets[sz] = mid;
         }
      }
      if(!forBuy && g_activeFVGs[i].isBullish) {
         double mid = (g_activeFVGs[i].top + g_activeFVGs[i].bottom) / 2.0;
         if(mid < currentPrice) {
            int sz = ArraySize(targets);
            ArrayResize(targets, sz + 1);
            targets[sz] = mid;
         }
      }
   }

   // 2) Opposing OBs as targets
   for(int i = 0; i < ArraySize(g_activeOBs); i++) {
      if(!g_activeOBs[i].isValid) continue;
      if(forBuy && !g_activeOBs[i].isBullish) {
         // Bearish OB above = supply zone target
         if(g_activeOBs[i].bottom > currentPrice) {
            int sz = ArraySize(targets);
            ArrayResize(targets, sz + 1);
            targets[sz] = g_activeOBs[i].bottom; // Enter at bottom of supply
         }
      }
      if(!forBuy && g_activeOBs[i].isBullish) {
         if(g_activeOBs[i].top < currentPrice) {
            int sz = ArraySize(targets);
            ArrayResize(targets, sz + 1);
            targets[sz] = g_activeOBs[i].top; // Enter at top of demand
         }
      }
   }

   // 3) Swing H/L liquidity levels
   for(int i = 5; i < 60; i++) {
      if(forBuy) {
         bool isSwingHigh = true;
         double high = iHigh(Symbol(), PERIOD_M5, i);
         for(int j = 1; j <= 2; j++) {
            if(iHigh(Symbol(), PERIOD_M5, i - j) >= high ||
               iHigh(Symbol(), PERIOD_M5, i + j) >= high) {
               isSwingHigh = false;
               break;
            }
         }
         if(isSwingHigh && high > currentPrice) {
            int sz = ArraySize(targets);
            ArrayResize(targets, sz + 1);
            targets[sz] = high;
         }
      }
      else {
         bool isSwingLow = true;
         double low = iLow(Symbol(), PERIOD_M5, i);
         for(int j = 1; j <= 2; j++) {
            if(iLow(Symbol(), PERIOD_M5, i - j) <= low ||
               iLow(Symbol(), PERIOD_M5, i + j) <= low) {
               isSwingLow = false;
               break;
            }
         }
         if(isSwingLow && low < currentPrice) {
            int sz = ArraySize(targets);
            ArrayResize(targets, sz + 1);
            targets[sz] = low;
         }
      }
   }

   // --- Sort targets by distance (closest first) ---
   for(int i = 0; i < ArraySize(targets) - 1; i++) {
      for(int j = i + 1; j < ArraySize(targets); j++) {
         double dist_i = MathAbs(targets[i] - currentPrice);
         double dist_j = MathAbs(targets[j] - currentPrice);
         if(dist_j < dist_i) {
            double tmp = targets[i];
            targets[i] = targets[j];
            targets[j] = tmp;
         }
      }
   }

   // --- Assign TP1 and TP2 ---
   // TP1 = first target that gives at least 1.5R
   // TP2 = next target that gives at least MinRR
   for(int i = 0; i < ArraySize(targets); i++) {
      double rr = MathAbs(targets[i] - entry) / slDist;
      if(tp1 == 0 && rr >= 1.5) {
         tp1 = targets[i];
      }
      else if(tp1 != 0 && tp2 == 0 && rr >= MinRR) {
         tp2 = targets[i];
         break;
      }
   }

   // Fallbacks
   if(tp1 == 0) {
      tp1 = forBuy ? entry + slDist * 1.5 : entry - slDist * 1.5;
   }
   if(tp2 == 0) {
      tp2 = forBuy ? entry + slDist * MinRR : entry - slDist * MinRR;
   }
}

// Legacy wrapper for RR check
double FindNextLiquidity(bool forBuy) {
   double bid = MarketInfo(Symbol(), MODE_BID);
   double ask = MarketInfo(Symbol(), MODE_ASK);
   double tp1 = 0, tp2 = 0;
   FindTPLevels(forBuy, forBuy ? ask : bid, 0, tp1, tp2);
   return tp2 != 0 ? tp2 : tp1;
}

//+------------------------------------------------------------------+
//| EXECUTE TRADE                                                     |
//+------------------------------------------------------------------+
void ExecuteTrade(int type, double price, double sl, double tp, string comment) {
   double lotSize = CalculateLotSize(MathAbs(price - sl));

   if(lotSize <= 0) {
      Print("Lot size invalid: ", lotSize);
      return;
   }

   price = NormalizeDouble(price, g_digits);
   sl    = NormalizeDouble(sl, g_digits);
   tp    = NormalizeDouble(tp, g_digits);

   // Store initial risk distance in comment for later use
   double initialRisk = MathAbs(price - sl);
   string fullComment = comment + "|R=" + DoubleToStr(initialRisk, g_digits);

   int ticket = OrderSend(Symbol(), type, lotSize, price, 3, sl, tp,
                           fullComment, MagicNumber, 0,
                           type == OP_BUY ? clrGreen : clrRed);

   if(ticket < 0) {
      Print("OrderSend failed: ", GetLastError(),
            " | Type: ", type,
            " | Price: ", price,
            " | SL: ", sl,
            " | TP: ", tp,
            " | Lots: ", lotSize);
   }
   else {
      Print("Trade opened #", ticket,
            " | ", comment,
            " | Lots: ", lotSize,
            " | SL: ", sl,
            " | TP: ", tp,
            " | RR: ", DoubleToStr(MathAbs(tp - price) / MathAbs(price - sl), 1));
   }
}

//+------------------------------------------------------------------+
//| CALCULATE LOT SIZE (Risk-based)                                  |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistance) {
   if(slDistance <= 0) return 0;

   double riskMoney = AccountBalance() * RiskPercent / 100.0;
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);

   if(tickValue == 0 || tickSize == 0) return 0;

   double slTicks = slDistance / tickSize;
   double lotSize = riskMoney / (slTicks * tickValue);

   double minLot  = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot  = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);

   lotSize = MathFloor(lotSize / lotStep) * lotStep;
   lotSize = MathMax(minLot, MathMin(maxLot, lotSize));

   return NormalizeDouble(lotSize, 2);
}

//+------------------------------------------------------------------+
//| CHECK IF TICKET ALREADY HAD TP1 PARTIAL CLOSE                    |
//+------------------------------------------------------------------+
bool HasTP1Fired(int ticket) {
   for(int i = 0; i < g_tp1Count; i++) {
      if(g_tp1Tickets[i] == ticket) return true;
   }
   return false;
}

void MarkTP1Fired(int ticket) {
   g_tp1Count++;
   ArrayResize(g_tp1Tickets, g_tp1Count);
   g_tp1Tickets[g_tp1Count - 1] = ticket;
}

//+------------------------------------------------------------------+
//| GET INITIAL RISK from order comment (stored as "|R=0.00123")     |
//+------------------------------------------------------------------+
double GetInitialRisk(string comment, double fallback) {
   int pos = StringFind(comment, "|R=");
   if(pos < 0) return fallback;
   string rStr = StringSubstr(comment, pos + 3);
   double r = StringToDouble(rStr);
   return (r > 0) ? r : fallback;
}

//+------------------------------------------------------------------+
//| MANAGE OPEN TRADES (Partial Close + BE + Trailing)               |
//+------------------------------------------------------------------+
void ManageOpenTrades() {
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      double lots      = OrderLots();
      int    ticket    = OrderTicket();
      string comment   = OrderComment();

      // Use initial risk from comment (not current SL which may have moved)
      double riskDist = GetInitialRisk(comment, MathAbs(openPrice - currentSL));
      if(riskDist <= 0) continue;

      bool tp1Done = HasTP1Fired(ticket);
      // If SL is already near breakeven, TP1 already fired on parent ticket
      if(!tp1Done && MathAbs(currentSL - openPrice) < 2 * g_pipValue && currentSL != 0)
         tp1Done = true;

      if(OrderType() == OP_BUY) {
         double currentPrice = MarketInfo(Symbol(), MODE_BID);
         double profit = currentPrice - openPrice;

         // TP1: Partial close 50% at 1.5R, move SL to breakeven
         if(UsePartialClose && !tp1Done && profit >= riskDist * 1.5) {
            double closeLots = NormalizeDouble(lots * TP1_Percent / 100.0, 2);
            double minLot = MarketInfo(Symbol(), MODE_MINLOT);
            if(closeLots >= minLot && (lots - closeLots) >= minLot) {
               if(OrderClose(ticket, closeLots, currentPrice, 3, clrOrange)) {
                  MarkTP1Fired(ticket);
                  Print("TP1 hit #", ticket, " | Closed ", closeLots, " lots @ ", currentPrice,
                        " | Profit: ", DoubleToStr(closeLots * profit / Point * MarketInfo(Symbol(), MODE_TICKVALUE) * Point, 2));
                  // Move SL to breakeven + 1 pip
                  if(OrderSelect(ticket, SELECT_BY_TICKET)) {
                     double beSL = openPrice + 1 * g_pipValue;
                     if(!OrderModify(ticket, openPrice, beSL, OrderTakeProfit(), 0, clrYellow))
                        Print("OrderModify BE failed #", ticket, " error=", GetLastError());
                  }
               }
            }
         }

         // Breakeven at 1R (if TP1 not used)
         if(UseBreakeven && !tp1Done && profit >= riskDist && currentSL < openPrice) {
            ModifySL(ticket, openPrice + 1 * g_pipValue);
         }

         // Trailing stop
         if(UseTrailingStop && profit >= riskDist * TrailingRMultiple) {
            double trailDist = riskDist * 0.3;
            double trailSL = currentPrice - trailDist;
            if(trailSL > currentSL && trailSL > openPrice) {
               ModifySL(ticket, trailSL);
            }
         }
      }
      else if(OrderType() == OP_SELL) {
         double currentPrice = MarketInfo(Symbol(), MODE_ASK);
         double profit = openPrice - currentPrice;

         // TP1: Partial close 50% at 1.5R, move SL to breakeven
         if(UsePartialClose && !tp1Done && profit >= riskDist * 1.5) {
            double closeLots = NormalizeDouble(lots * TP1_Percent / 100.0, 2);
            double minLot = MarketInfo(Symbol(), MODE_MINLOT);
            if(closeLots >= minLot && (lots - closeLots) >= minLot) {
               if(OrderClose(ticket, closeLots, currentPrice, 3, clrOrange)) {
                  MarkTP1Fired(ticket);
                  Print("TP1 hit #", ticket, " | Closed ", closeLots, " lots @ ", currentPrice);
                  // Move SL to breakeven - 1 pip
                  if(OrderSelect(ticket, SELECT_BY_TICKET)) {
                     double beSL = openPrice - 1 * g_pipValue;
                     if(!OrderModify(ticket, openPrice, beSL, OrderTakeProfit(), 0, clrYellow))
                        Print("OrderModify BE failed #", ticket, " error=", GetLastError());
                  }
               }
            }
         }

         // Breakeven at 1R (if TP1 not used)
         if(UseBreakeven && !tp1Done && profit >= riskDist && currentSL > openPrice) {
            ModifySL(ticket, openPrice - 1 * g_pipValue);
         }

         // Trailing stop
         if(UseTrailingStop && profit >= riskDist * TrailingRMultiple) {
            double trailDist = riskDist * 0.3;
            double trailSL = currentPrice + trailDist;
            if(trailSL < currentSL && trailSL < openPrice) {
               ModifySL(ticket, trailSL);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| MODIFY STOP LOSS                                                  |
//+------------------------------------------------------------------+
void ModifySL(int ticket, double newSL) {
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;

   newSL = NormalizeDouble(newSL, g_digits);

   if(MathAbs(newSL - OrderStopLoss()) < Point) return;

   bool result = OrderModify(ticket, OrderOpenPrice(), newSL,
                              OrderTakeProfit(), 0, clrYellow);
   if(!result) {
      Print("OrderModify failed for #", ticket, " | Error: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| NEWS FILTER - Load CSV Calendar                                  |
//| Format: YYYY.MM.DD,HH:MM,CURRENCY,IMPACT,TITLE                  |
//| Example: 2024.04.05,14:30,USD,HIGH,Non-Farm Payrolls             |
//+------------------------------------------------------------------+
void LoadNewsCalendar() {
   ArrayResize(g_newsEvents, 0);
   g_lastNewsLoad = TimeCurrent();

   int handle = FileOpen(NewsFile, FILE_READ | FILE_CSV, ',');
   if(handle == INVALID_HANDLE) {
      Print("News file not found: ", NewsFile,
            " | Using built-in recurring events only");
      LoadRecurringNews();
      return;
   }

   int count = 0;
   while(!FileIsEnding(handle)) {
      string dateStr   = FileReadString(handle);
      string timeStr   = FileReadString(handle);
      string currency  = FileReadString(handle);
      string impact    = FileReadString(handle);
      string title     = FileReadString(handle);

      if(StringLen(dateStr) < 8) continue;

      datetime eventTime = StringToTime(dateStr + " " + timeStr);
      if(eventTime == 0) continue;

      // Only load future events or events from today
      if(eventTime < TimeCurrent() - 86400) continue;

      // Only HIGH impact
      if(impact != "HIGH") continue;

      int size = ArraySize(g_newsEvents);
      ArrayResize(g_newsEvents, size + 1);
      g_newsEvents[size].time = eventTime;
      g_newsEvents[size].currency = currency;
      g_newsEvents[size].impact = impact;
      g_newsEvents[size].title = title;
      count++;
   }

   FileClose(handle);
   Print("Loaded ", count, " high-impact news events");

   // Add recurring events on top
   LoadRecurringNews();
}

//+------------------------------------------------------------------+
//| LOAD RECURRING HIGH-IMPACT NEWS (built-in safety net)            |
//+------------------------------------------------------------------+
void LoadRecurringNews() {
   datetime now = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now, dt);
   string yr = IntegerToString(dt.year);
   string mo = IntegerToString(dt.mon);

   // NFP: First Friday of the month at 14:30
   datetime firstOfMonth = StringToTime(yr + "." + mo + ".01 14:30");
   MqlDateTime fomDt;
   TimeToStruct(firstOfMonth, fomDt);
   int daysToFriday = (5 - fomDt.day_of_week + 7) % 7;
   if(daysToFriday == 0 && fomDt.day_of_week != 5) daysToFriday = 7;
   datetime nfpDate = firstOfMonth + daysToFriday * 86400;
   AddRecurringEvent(nfpDate, "USD", "Non-Farm Payrolls");

   // CPI: Usually around 13th at 14:30
   datetime cpiDate = StringToTime(yr + "." + mo + ".13 14:30");
   AddRecurringEvent(cpiDate, "USD", "CPI");

   // FOMC: 8 fixed meetings per year (actual 2025-2026 schedule)
   // Only the announcement day matters (Wednesday 20:00 server time)
   string fomcDates[] = {
      // 2025
      "2025.01.29","2025.03.19","2025.05.07","2025.06.18",
      "2025.07.30","2025.09.17","2025.10.29","2025.12.17",
      // 2026
      "2026.01.28","2026.03.18","2026.04.29","2026.06.17",
      "2026.07.29","2026.09.16","2026.10.28","2026.12.16"
   };
   for(int i = 0; i < ArraySize(fomcDates); i++) {
      datetime fomcTime = StringToTime(fomcDates[i] + " 20:00");
      // Only add if within 7 days of now
      if(MathAbs((double)(fomcTime - now)) < 7 * 86400)
         AddRecurringEvent(fomcTime, "USD", "FOMC");
   }

   // ECB: ~6 fixed meetings per year (actual 2025-2026 schedule)
   string ecbDates[] = {
      // 2025
      "2025.01.30","2025.03.06","2025.04.17","2025.06.05",
      "2025.07.24","2025.09.11","2025.10.30","2025.12.18",
      // 2026
      "2026.01.22","2026.03.05","2026.04.16","2026.06.04",
      "2026.07.16","2026.09.10","2026.10.29","2026.12.17"
   };
   for(int i = 0; i < ArraySize(ecbDates); i++) {
      datetime ecbTime = StringToTime(ecbDates[i] + " 14:15");
      if(MathAbs((double)(ecbTime - now)) < 7 * 86400)
         AddRecurringEvent(ecbTime, "EUR", "ECB Rate Decision");
   }

   Print("Recurring news loaded | Events in scope: ",
         ArraySize(g_newsEvents));
}

//+------------------------------------------------------------------+
//| ADD RECURRING NEWS EVENT                                         |
//+------------------------------------------------------------------+
void AddRecurringEvent(datetime eventTime, string currency, string title) {
   // Don't add if already past + buffer
   if(eventTime < TimeCurrent() - NewsMinutesAfter * 60) return;

   int size = ArraySize(g_newsEvents);
   ArrayResize(g_newsEvents, size + 1);
   g_newsEvents[size].time = eventTime;
   g_newsEvents[size].currency = currency;
   g_newsEvents[size].impact = "HIGH";
   g_newsEvents[size].title = title;
}

//+------------------------------------------------------------------+
//| CHECK IF WE ARE IN NEWS BLACKOUT WINDOW                          |
//+------------------------------------------------------------------+
bool IsNewsTime() {
   datetime now = TimeCurrent();
   string sym = Symbol();

   for(int i = 0; i < ArraySize(g_newsEvents); i++) {
      // Check if the news currency affects our symbol
      if(StringFind(sym, g_newsEvents[i].currency) < 0) continue;

      datetime newsStart = g_newsEvents[i].time - NewsMinutesBefore * 60;
      datetime newsEnd   = g_newsEvents[i].time + NewsMinutesAfter * 60;

      if(now >= newsStart && now <= newsEnd) {
         Print("NEWS FILTER: Blocking trade | ", g_newsEvents[i].title,
               " (", g_newsEvents[i].currency, ") at ",
               TimeToString(g_newsEvents[i].time));
         return true;
      }
   }
   return false;
}
//+------------------------------------------------------------------+
