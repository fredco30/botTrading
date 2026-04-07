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
// --- Risk Management ---
input double RiskPercent        = 1.0;     // Risk % per trade
input double MaxSpreadPips      = 3.0;     // Max spread allowed (pips)
input int    MagicNumber        = 20240407;// Magic number
input int    MaxOpenTrades      = 1;       // Max simultaneous trades
input double MinRR              = 2.0;     // Minimum Risk:Reward ratio

// --- Structure Detection (M15) ---
input int    StructureLookback  = 20;      // Bars to look back for swing H/L
input int    SwingStrength      = 3;       // Bars on each side for swing point

// --- Order Block Detection (M5) ---
input int    OB_Lookback        = 30;      // Bars to scan for OB
input double OB_MinBodyRatio    = 0.5;     // Min body/range ratio for impulse candle
input int    OB_MinImpulsePips  = 10;      // Min impulse move (pips)

// --- FVG Detection (M5) ---
input int    FVG_Lookback       = 20;      // Bars to scan for FVG
input double FVG_MinSizePips    = 3.0;     // Min FVG size (pips)

// --- Liquidity Sweep ---
input int    LiqSweep_Lookback  = 30;      // Bars to scan for liq levels
input double LiqSweep_MinPips   = 2.0;     // Min sweep beyond level (pips)

// --- Session Filter ---
input int    LondonStartHour    = 8;       // London session start (server time)
input int    LondonEndHour      = 12;      // London session end
input int    NYStartHour        = 13;      // New York session start
input int    NYEndHour          = 17;      // New York session end

// --- Trade Management ---
input bool   UseBreakeven       = true;    // Move SL to BE after 1R
input bool   UseTrailingStop    = false;   // Trail stop after 1.5R
input double TrailingRMultiple  = 1.5;     // R-multiple to start trailing
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

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(g_digits == 3 || g_digits == 5)
      g_pipValue = Point * 10;
   else
      g_pipValue = Point;

   if(UseNewsFilter) LoadNewsCalendar();

   Print("SMC Scalper EA initialized | Symbol: ", Symbol(),
         " | Pip value: ", g_pipValue,
         " | Risk: ", RiskPercent, "%",
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
   // --- New bar check (M5) ---
   datetime currentBarTime = iTime(Symbol(), PERIOD_M5, 0);
   if(currentBarTime == g_lastBarTime) return;
   g_lastBarTime = currentBarTime;

   // --- Pre-checks ---
   if(!IsSessionActive()) return;
   if(SpreadTooWide()) return;
   if(UseNewsFilter && IsNewsTime()) return;
   if(CountOpenTrades() >= MaxOpenTrades) return;

   // Reload news file daily
   if(UseNewsFilter && TimeCurrent() - g_lastNewsLoad > 86400) LoadNewsCalendar();

   // --- Step 1: M15 Structure Analysis (BOS detection) ---
   AnalyzeStructure();

   // --- Step 2: M5 Order Block Detection ---
   DetectOrderBlocks();

   // --- Step 3: M5 FVG Detection ---
   DetectFVGs();

   // --- Step 4: Check for Liquidity Sweep ---
   bool liqSweepBull = DetectLiquiditySweep(true);
   bool liqSweepBear = DetectLiquiditySweep(false);

   // --- Step 5: Entry Logic ---
   CheckEntry(liqSweepBull, liqSweepBear);

   // --- Step 6: Trade Management ---
   ManageOpenTrades();
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
//| SPREAD CHECK                                                      |
//+------------------------------------------------------------------+
bool SpreadTooWide() {
   double spread = MarketInfo(Symbol(), MODE_SPREAD) * Point / g_pipValue;
   return (spread > MaxSpreadPips);
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

   FindSwingPoints(PERIOD_M15, StructureLookback, SwingStrength, swingHighs, swingLows);

   if(ArraySize(swingHighs) < 2 || ArraySize(swingLows) < 2) {
      g_currentBias = BIAS_NONE;
      return;
   }

   g_lastSwingHigh = swingHighs[0];
   g_prevSwingHigh = swingHighs[1];
   g_lastSwingLow  = swingLows[0];
   g_prevSwingLow  = swingLows[1];

   double currentClose = iClose(Symbol(), PERIOD_M15, 0);

   // Bullish BOS: price breaks above last swing high + higher lows
   if(currentClose > g_lastSwingHigh.price &&
      g_lastSwingLow.price > g_prevSwingLow.price) {
      g_currentBias = BIAS_BULLISH;
   }
   // Bearish BOS: price breaks below last swing low + lower highs
   else if(currentClose < g_lastSwingLow.price &&
           g_lastSwingHigh.price < g_prevSwingHigh.price) {
      g_currentBias = BIAS_BEARISH;
   }
   // HH + HL = bullish trend
   else if(g_lastSwingHigh.price > g_prevSwingHigh.price &&
           g_lastSwingLow.price > g_prevSwingLow.price) {
      g_currentBias = BIAS_BULLISH;
   }
   // LH + LL = bearish trend
   else if(g_lastSwingHigh.price < g_prevSwingHigh.price &&
           g_lastSwingLow.price < g_prevSwingLow.price) {
      g_currentBias = BIAS_BEARISH;
   }
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

   for(int i = 2; i < OB_Lookback; i++) {
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

      if(impMovePips < OB_MinImpulsePips) continue;
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
         if(gapSize >= FVG_MinSizePips) {
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
         if(gapSize >= FVG_MinSizePips) {
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
         if(low_i < liqLevel - LiqSweep_MinPips * g_pipValue &&
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
         if(high_i > liqLevel + LiqSweep_MinPips * g_pipValue &&
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

   // --- BULLISH ENTRY ---
   if(g_currentBias == BIAS_BULLISH) {
      for(int i = 0; i < ArraySize(g_activeOBs); i++) {
         if(!g_activeOBs[i].isBullish || !g_activeOBs[i].isValid) continue;

         // Price in OB zone
         if(bid <= g_activeOBs[i].top && bid >= g_activeOBs[i].bottom) {
            bool hasFVG = HasFVGConfluence(g_activeOBs[i], true);

            // Minimum confluence: OB + (FVG or liq sweep)
            if(hasFVG || liqSweepBull) {
               double sl = g_activeOBs[i].bottom - 2 * g_pipValue;
               double tp1 = 0, tp2 = 0;
               FindTPLevels(true, ask, sl, tp1, tp2);

               double rr = (tp2 - ask) / (ask - sl);
               if(rr >= MinRR) {
                  ExecuteTrade(OP_BUY, ask, sl, tp2,
                              "SMC Buy|OB" + (hasFVG ? "+FVG" : "") +
                              (liqSweepBull ? "+Sweep" : ""));
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

         if(ask >= g_activeOBs[i].bottom && ask <= g_activeOBs[i].top) {
            bool hasFVG = HasFVGConfluence(g_activeOBs[i], false);

            if(hasFVG || liqSweepBear) {
               double sl = g_activeOBs[i].top + 2 * g_pipValue;
               double tp1 = 0, tp2 = 0;
               FindTPLevels(false, bid, sl, tp1, tp2);

               double rr = (bid - tp2) / (sl - bid);
               if(rr >= MinRR) {
                  ExecuteTrade(OP_SELL, bid, sl, tp2,
                              "SMC Sell|OB" + (hasFVG ? "+FVG" : "") +
                              (liqSweepBear ? "+Sweep" : ""));
                  g_activeOBs[i].isValid = false;
                  return;
               }
            }
         }
      }
   }
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

   int ticket = OrderSend(Symbol(), type, lotSize, price, 3, sl, tp,
                           comment, MagicNumber, 0,
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
//| MANAGE OPEN TRADES (Partial Close + BE + Trailing)               |
//+------------------------------------------------------------------+
void ManageOpenTrades() {
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      double riskDist  = MathAbs(openPrice - currentSL);
      double lots      = OrderLots();
      int    ticket    = OrderTicket();
      string comment   = OrderComment();

      if(OrderType() == OP_BUY) {
         double currentPrice = MarketInfo(Symbol(), MODE_BID);
         double profit = currentPrice - openPrice;

         // Partial close at TP1 (1.5R) — close 50%, move SL to BE
         if(UsePartialClose && profit >= riskDist * 1.5
            && StringFind(comment, "[TP1]") < 0) {
            double closeLots = NormalizeDouble(lots * TP1_Percent / 100.0,
                                               2);
            double minLot = MarketInfo(Symbol(), MODE_MINLOT);
            if(closeLots >= minLot && (lots - closeLots) >= minLot) {
               if(OrderClose(ticket, closeLots, currentPrice, 3, clrOrange)) {
                  Print("TP1 partial close #", ticket, " | ", closeLots, " lots @ ", currentPrice);
                  // Update comment on remaining position
                  if(OrderSelect(ticket, SELECT_BY_TICKET)) {
                     OrderModify(ticket, openPrice,
                                 openPrice + 1 * g_pipValue,
                                 OrderTakeProfit(), 0, clrYellow);
                  }
               }
            }
         }

         // Breakeven at 1R
         if(UseBreakeven && profit >= riskDist && currentSL < openPrice) {
            ModifySL(ticket, openPrice + 1 * g_pipValue);
         }

         // Trailing after TrailingRMultiple
         if(UseTrailingStop && profit >= riskDist * TrailingRMultiple) {
            double trailSL = currentPrice - riskDist * 0.5;
            if(trailSL > currentSL) {
               ModifySL(ticket, trailSL);
            }
         }
      }
      else if(OrderType() == OP_SELL) {
         double currentPrice = MarketInfo(Symbol(), MODE_ASK);
         double profit = openPrice - currentPrice;

         // Partial close at TP1
         if(UsePartialClose && profit >= riskDist * 1.5
            && StringFind(comment, "[TP1]") < 0) {
            double closeLots = NormalizeDouble(lots * TP1_Percent / 100.0,
                                               2);
            double minLot = MarketInfo(Symbol(), MODE_MINLOT);
            if(closeLots >= minLot && (lots - closeLots) >= minLot) {
               if(OrderClose(ticket, closeLots, currentPrice, 3, clrOrange)) {
                  Print("TP1 partial close #", ticket, " | ", closeLots, " lots @ ", currentPrice);
                  if(OrderSelect(ticket, SELECT_BY_TICKET)) {
                     OrderModify(ticket, openPrice,
                                 openPrice - 1 * g_pipValue,
                                 OrderTakeProfit(), 0, clrYellow);
                  }
               }
            }
         }

         if(UseBreakeven && profit >= riskDist && currentSL > openPrice) {
            ModifySL(ticket, openPrice - 1 * g_pipValue);
         }

         if(UseTrailingStop && profit >= riskDist * TrailingRMultiple) {
            double trailSL = currentPrice + riskDist * 0.5;
            if(trailSL < currentSL) {
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
   // Get current week's dates
   datetime now = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now, dt);

   // Find first day of current week (Monday)
   int dayOfWeek = dt.day_of_week;
   if(dayOfWeek == 0) dayOfWeek = 7; // Sunday = 7
   datetime monday = now - (dayOfWeek - 1) * 86400;

   // NFP: First Friday of the month at 14:30 server time (usually 8:30 ET)
   datetime firstOfMonth = StringToTime(IntegerToString(dt.year) + "." +
                                         IntegerToString(dt.mon) + ".01 14:30");
   MqlDateTime fomDt;
   TimeToStruct(firstOfMonth, fomDt);
   int daysToFriday = (5 - fomDt.day_of_week + 7) % 7;
   if(daysToFriday == 0 && fomDt.day_of_week != 5) daysToFriday = 7;
   datetime nfpDate = firstOfMonth + daysToFriday * 86400;
   AddRecurringEvent(nfpDate, "USD", "Non-Farm Payrolls");

   // CPI: Usually around 13th at 14:30
   datetime cpiDate = StringToTime(IntegerToString(dt.year) + "." +
                                    IntegerToString(dt.mon) + ".13 14:30");
   AddRecurringEvent(cpiDate, "USD", "CPI");

   // FOMC: Check if there's a Wednesday meeting this week (8 meetings/year)
   // We flag all Wednesdays at 20:00 as potential FOMC
   datetime wednesday = monday + 2 * 86400;
   MqlDateTime wedDt;
   TimeToStruct(wednesday, wedDt);
   datetime fomcTime = StringToTime(TimeToString(wednesday, TIME_DATE) + " 20:00");
   // Only add if it's this week and within FOMC months (Jan,Mar,May,Jun,Jul,Sep,Nov,Dec)
   int fomcMonths[] = {1,3,5,6,7,9,11,12};
   for(int m = 0; m < ArraySize(fomcMonths); m++) {
      if(dt.mon == fomcMonths[m]) {
         AddRecurringEvent(fomcTime, "USD", "FOMC");
         break;
      }
   }

   // ECB Rate Decision: Usually Thursday at 14:15
   datetime thursday = monday + 3 * 86400;
   datetime ecbTime = StringToTime(TimeToString(thursday, TIME_DATE) + " 14:15");
   // ECB meets ~every 6 weeks, simplified: flag if day < 15
   if(dt.day < 15) {
      AddRecurringEvent(ecbTime, "EUR", "ECB Rate Decision");
   }
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
