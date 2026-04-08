//+------------------------------------------------------------------+
//|                                          EMA_Pullback_EA.mq4     |
//|                    EMA Pullback Trend Following - MT4              |
//|                    H1 Trend + M15 Pullback Entry                   |
//+------------------------------------------------------------------+
#property copyright "EMA Pullback EA"
#property link      ""
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| INPUTS                                                            |
//+------------------------------------------------------------------+
// --- Preset ---
enum INSTRUMENT_PRESET {
   PRESET_EURUSD = 0,   // EURUSD (optimized, default)
   PRESET_GBPUSD = 1,   // GBPUSD (aggressive filter)
   PRESET_XAUUSD = 2    // XAUUSD / Gold
};
input INSTRUMENT_PRESET Preset  = PRESET_EURUSD; // Instrument preset

// --- Timeframe Mode ---
enum TF_MODE {
   TF_H1_M15  = 0,      // H1 trend + M15 entry (default)
   TF_H4_M30  = 1       // H4 trend + M30 entry (swing)
};
input TF_MODE TimeframeMode     = TF_H1_M15;    // Timeframe combination

// --- Risk Management ---
input double RiskPercent        = 1.0;     // Risk % per trade
input double MaxSpreadPips      = 3.0;     // Max spread allowed (pips)
input int    MagicNumber        = 20250407;// Magic number
input double MinRR              = 2.5;     // Minimum Risk:Reward ratio
input double MinSL_Pips         = 15.0;    // Minimum SL distance (pips) — was 10, raised to filter weak setups
input double MaxSL_Pips         = 25.0;    // Maximum SL distance (pips) — was 30, tightened (25-30 bucket PF=0.98)

// --- Trend Filter (H1) ---
input int    TrendEMA_Period    = 50;      // H1 EMA period for trend direction
input int    TrendBars          = 5;       // H1 EMA must slope for X bars

// --- Entry (M15) ---
input int    EntryEMA_Period    = 20;      // M15 EMA period for pullback
input int    SL_SwingBars       = 3;       // Bars to look back for SL swing
input int    RSI_Period         = 14;      // RSI period for overbought/oversold filter
input int    RSI_OB             = 70;      // RSI overbought level (don't buy above)
input int    RSI_OS             = 30;      // RSI oversold level (don't sell below)

// --- Session Filter ---
input int    LondonStartHour    = 8;       // London session start (server time)
input int    LondonEndHour      = 12;      // London session end
input int    NYStartHour        = 13;      // New York session start
input int    NYEndHour          = 17;      // New York session end

// --- Trade Management ---
input bool   UseBreakeven       = true;    // Move SL to BE
input double BE_Trigger_R       = 1.5;     // Move SL to BE after X * R (1.5 = more room)
input int    MaxTradesPerDay    = 2;       // Max trades per day

// --- Volatility Filter (ATR) ---
input bool   UseATRFilter       = true;    // Only trade when ATR > threshold
input int    ATR_Period          = 14;      // ATR period on H1
input double ATR_MinPips         = 9.0;    // Min ATR in pips — was 6, raised per analysis
input double ATR_MaxPips         = 19.0;   // Max ATR in pips — 0 wins above 19 in 2025-2026

// --- Pullback Quality Filter ---
input bool   UseEMA50DistFilter  = true;   // Block entries too far from EMA50
input double MaxEMA50DistPips    = 30.0;   // Max distance from H1 EMA50 (winners avg 23, losers avg 35)

// --- Day/Hour Filters ---
input bool   BlockFriday         = true;   // Do not trade on Friday
input bool   BlockHour13         = true;   // Do not trade at 13:00 (NY open chaos)
input string BlockedHours        = "13";   // Comma-separated hours to block (server time)
input bool   BlockToxicCombos    = true;   // Block worst hour+day combos from analysis
input bool   ReduceThursdayRisk  = true;   // Halve risk on Thursday (weakest day PF=1.08)
input double ThursdayRiskMult    = 0.5;    // Thursday risk multiplier (0.5 = half risk)

//+------------------------------------------------------------------+
//| GLOBALS                                                           |
//+------------------------------------------------------------------+
double     g_pipValue;
int        g_digits;
datetime   g_lastBarTime = 0;
datetime   g_currentDay  = 0;
int        g_dailyTrades = 0;

// --- Runtime params (overridden by preset) ---
double  r_MaxSpreadPips;
double  r_MinRR;
double  r_MinSL_Pips;
double  r_MaxSL_Pips;
double  r_ATR_MinPips;
double  r_ATR_MaxPips;
double  r_MaxEMA50DistPips;
double  r_BE_Trigger_R;
int     r_LondonStartHour;
int     r_LondonEndHour;
int     r_NYStartHour;
int     r_NYEndHour;
bool    r_UseLondonSession;
bool    r_BlockFriday;
bool    r_BlockMonday;
bool    r_BlockToxicCombos;
int     r_BlockedHoursArr[10];
int     r_BlockedHoursCount;
bool    r_ReduceThursdayRisk;
double  r_ThursdayRiskMult;
int     r_MaxTradesPerDay;
int     r_TrendBars;
int     r_SL_SwingBars;
int     r_TrendTF;      // PERIOD_H1 or PERIOD_H4
int     r_EntryTF;      // PERIOD_M15 or PERIOD_M30

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(g_digits == 3 || g_digits == 5)
      g_pipValue = Point * 10;
   else
      g_pipValue = Point;

   ApplyPreset();

   string presetName = "EURUSD";
   if(Preset == PRESET_GBPUSD) presetName = "GBPUSD (aggressive)";
   if(Preset == PRESET_XAUUSD) presetName = "XAUUSD/Gold";
   string tfMode = (TimeframeMode == TF_H4_M30) ? "H4+M30 (swing)" : "H1+M15 (intraday)";
   Print("EMA Pullback EA v3 initialized | Symbol: ", Symbol(),
         " | Preset: ", presetName,
         " | TF: ", tfMode,
         " | Pip value: ", g_pipValue,
         " | SL range: ", DoubleToStr(r_MinSL_Pips, 0), "-", DoubleToStr(r_MaxSL_Pips, 0), " pips",
         " | ATR: ", UseATRFilter ? DoubleToStr(r_ATR_MinPips, 0) + "-" + DoubleToStr(r_ATR_MaxPips, 0) + " pips" : "OFF",
         " | EMA50 dist max: ", UseEMA50DistFilter ? DoubleToStr(r_MaxEMA50DistPips, 0) + " pips" : "OFF",
         " | Friday: ", r_BlockFriday ? "BLOCKED" : "allowed",
         " | Spread max: ", DoubleToStr(r_MaxSpreadPips, 1),
         " | BE trigger: ", DoubleToStr(r_BE_Trigger_R, 1), "R");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| APPLY PRESET                                                      |
//+------------------------------------------------------------------+
void ApplyPreset() {
   // Default: copy inputs to runtime
   r_MaxSpreadPips     = MaxSpreadPips;
   r_MinRR             = MinRR;
   r_MinSL_Pips        = MinSL_Pips;
   r_MaxSL_Pips        = MaxSL_Pips;
   r_ATR_MinPips       = ATR_MinPips;
   r_ATR_MaxPips       = ATR_MaxPips;
   r_MaxEMA50DistPips  = MaxEMA50DistPips;
   r_BE_Trigger_R      = BE_Trigger_R;
   r_LondonStartHour   = LondonStartHour;
   r_LondonEndHour     = LondonEndHour;
   r_NYStartHour       = NYStartHour;
   r_NYEndHour         = NYEndHour;
   r_UseLondonSession  = true;
   r_BlockFriday       = BlockFriday;
   r_BlockMonday       = false;
   r_BlockToxicCombos  = BlockToxicCombos;
   r_ReduceThursdayRisk = ReduceThursdayRisk;
   r_ThursdayRiskMult  = ThursdayRiskMult;
   r_MaxTradesPerDay   = MaxTradesPerDay;
   r_TrendBars         = TrendBars;
   r_SL_SwingBars      = SL_SwingBars;
   r_TrendTF           = PERIOD_H1;
   r_EntryTF           = PERIOD_M15;
   r_BlockedHoursCount = 0;
   ArrayInitialize(r_BlockedHoursArr, -1);

   // --- Timeframe Mode ---
   if(TimeframeMode == TF_H4_M30) {
      r_TrendTF        = PERIOD_H4;
      r_EntryTF        = PERIOD_M30;
      r_MinSL_Pips     = 25.0;     // Wider SL for M30 entries
      r_MaxSL_Pips     = 50.0;     // Wider range
      r_ATR_MinPips    = 12.0;     // Higher ATR threshold for H4
      r_ATR_MaxPips    = 30.0;     // H4 ATR can be wider
      r_MaxEMA50DistPips = 50.0;   // H4 price moves further from EMA50
      r_MaxTradesPerDay = 1;       // Less frequent on higher TF
      r_SL_SwingBars   = 4;        // Wider swing lookback
      Print("Timeframe H4+M30 (swing mode) applied | SL: 25-50 pips | ATR min: 12");
   }

   // --- XAUUSD / GOLD PRESET ---
   if(Preset == PRESET_XAUUSD) {
      r_MaxSpreadPips     = 8.0;       // Gold spread is wider
      r_MinSL_Pips        = 50.0;      // Gold moves ~5x more than EURUSD
      r_MaxSL_Pips        = 120.0;     // Wider range for gold
      r_ATR_MinPips       = 20.0;      // Gold ATR is much larger
      r_ATR_MaxPips       = 80.0;      // Gold can have high ATR normally
      r_MaxEMA50DistPips  = 150.0;     // Gold moves further from EMA50
      r_MinRR             = 2.5;       // Keep same RR
      r_BE_Trigger_R      = 1.5;       // Same BE logic
      r_LondonStartHour   = 8;         // Gold active during London
      r_LondonEndHour     = 12;
      r_NYStartHour       = 13;
      r_NYEndHour         = 18;        // Gold stays active longer in NY
      r_UseLondonSession  = true;
      r_BlockFriday       = true;      // Gold is erratic on Fridays too
      r_BlockMonday       = false;
      r_BlockToxicCombos  = false;     // EURUSD-specific, don't apply to gold
      r_ReduceThursdayRisk = false;    // Not validated for gold
      r_ThursdayRiskMult  = 1.0;
      r_MaxTradesPerDay   = 2;
      r_TrendBars         = 5;
      r_SL_SwingBars      = 4;         // Wider swing lookback for gold volatility
      Print("Preset XAUUSD/Gold applied | SL: 50-120 pips | ATR min: 20 | Spread max: 8");
   }

   // --- GBPUSD PRESET (aggressive filter, validated on 732 trades) ---
   if(Preset == PRESET_GBPUSD) {
      r_MaxSpreadPips     = 4.0;       // GBPUSD spread slightly wider than EURUSD
      r_MinSL_Pips        = 20.0;      // Below 20 pips = destroyed (PF<0.5)
      r_MaxSL_Pips        = 25.0;      // Keep tight
      r_ATR_MinPips       = 9.0;       // Same min as EURUSD
      r_ATR_MaxPips       = 22.0;      // GBPUSD sweet spot 18-22 pips
      r_MaxEMA50DistPips  = 50.0;      // GBPUSD moves further than EURUSD
      r_MinRR             = 2.5;       // Keep same
      r_BE_Trigger_R      = 1.5;       // Same BE logic
      r_LondonStartHour   = 9;         // Skip 08h (PF=0.58, -$1,923)
      r_LondonEndHour     = 12;
      r_NYStartHour       = 14;        // Skip 13h (already blocked) and avoid 15h start
      r_NYEndHour         = 17;
      r_UseLondonSession  = true;
      r_BlockFriday       = true;      // Friday PF=0.62, -$2,628
      r_BlockMonday       = true;      // Monday PF=0.71, -$2,258
      r_BlockToxicCombos  = true;      // Use GBPUSD-specific combos
      r_ReduceThursdayRisk = false;    // Not validated on GBPUSD
      r_ThursdayRiskMult  = 1.0;
      r_MaxTradesPerDay   = 2;
      r_TrendBars         = 5;
      r_SL_SwingBars      = 3;

      // Block 08h and 15h specifically
      r_BlockedHoursCount = 2;
      r_BlockedHoursArr[0] = 8;        // 08h: PF=0.58, -$1,923
      r_BlockedHoursArr[1] = 15;       // 15h: PF=0.61, -$1,873

      Print("Preset GBPUSD (aggressive) applied",
            " | SL: 20-25 pips | ATR: 9-22 | EMA50 dist: <50",
            " | Block: Fri+Mon+08h+15h+combos");
   }
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   Print("EMA Pullback EA removed. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick() {
   // --- Manage open trades on every tick (breakeven) ---
   ManageOpenTrades();

   // --- New bar check (entry TF) ---
   datetime currentBarTime = iTime(Symbol(), r_EntryTF, 0);
   if(currentBarTime == g_lastBarTime) return;
   g_lastBarTime = currentBarTime;

   // --- Reset daily counter ---
   datetime today = TimeCurrent() - TimeCurrent() % 86400;
   if(today != g_currentDay) {
      g_dailyTrades = 0;
      g_currentDay = today;
   }

   // --- Pre-checks ---
   if(!IsSessionActive()) return;
   if(SpreadTooWide()) return;
   if(IsDayBlocked()) return;
   if(IsHourBlocked()) return;
   if(UseATRFilter && !IsVolatilityOK()) return;
   if(!IsEMA50DistanceOK()) return;
   if(CountOpenTrades() >= 1) return;
   if(g_dailyTrades >= r_MaxTradesPerDay) return;

   // --- Check for entry ---
   CheckEntry();
}

//+------------------------------------------------------------------+
//| SESSION FILTER                                                    |
//+------------------------------------------------------------------+
bool IsSessionActive() {
   int hour = TimeHour(TimeCurrent());
   if(r_UseLondonSession && hour >= r_LondonStartHour && hour < r_LondonEndHour) return true;
   if(hour >= r_NYStartHour && hour < r_NYEndHour) return true;
   return false;
}

//+------------------------------------------------------------------+
//| SPREAD CHECK                                                      |
//+------------------------------------------------------------------+
bool SpreadTooWide() {
   double spread = MarketInfo(Symbol(), MODE_SPREAD) * Point / g_pipValue;
   return (spread > r_MaxSpreadPips);
}

//+------------------------------------------------------------------+
//| DAY FILTER (block Friday)                                         |
//+------------------------------------------------------------------+
bool IsDayBlocked() {
   int dow = TimeDayOfWeek(TimeCurrent());
   if(r_BlockFriday && dow == 5) return true;
   if(r_BlockMonday && dow == 1) return true;
   return false;
}

//+------------------------------------------------------------------+
//| HOUR FILTER (block toxic hours)                                   |
//+------------------------------------------------------------------+
bool IsHourBlocked() {
   int hour = TimeHour(TimeCurrent());
   int dow  = TimeDayOfWeek(TimeCurrent());

   // Quick check for the main blocked hour
   if(BlockHour13 && hour == 13) return true;

   // Check preset-specific blocked hours array
   for(int i = 0; i < r_BlockedHoursCount; i++) {
      if(hour == r_BlockedHoursArr[i]) return true;
   }

   // Parse additional blocked hours from comma-separated string
   if(StringLen(BlockedHours) > 0) {
      string parts[];
      int count = StringSplit(BlockedHours, ',', parts);
      for(int i = 0; i < count; i++) {
         StringReplace(parts[i], " ", "");
         int blocked = (int)StringToInteger(parts[i]);
         if(hour == blocked) return true;
      }
   }

   // Block toxic hour+day combos
   if(r_BlockToxicCombos) {
      if(Preset == PRESET_EURUSD) {
         // EURUSD combos: 14h/Tue, 11h/Mon, 14h/Thu, 16h/Mon
         if(hour == 14 && dow == 2) return true;
         if(hour == 11 && dow == 1) return true;
         if(hour == 14 && dow == 4) return true;
         if(hour == 16 && dow == 1) return true;
      }
      if(Preset == PRESET_GBPUSD) {
         // GBPUSD worst combos from analysis (732 trades)
         if(hour ==  9 && dow == 2) return true;  // 09h/Tue
         if(hour == 10 && dow == 4) return true;  // 10h/Thu
         if(hour == 11 && dow == 2) return true;  // 11h/Tue
         if(hour == 11 && dow == 3) return true;  // 11h/Wed
         if(hour == 14 && dow == 2) return true;  // 14h/Tue
         if(hour == 14 && dow == 4) return true;  // 14h/Thu
         if(hour == 16 && dow == 2) return true;  // 16h/Tue
         if(hour == 16 && dow == 3) return true;  // 16h/Wed
         if(hour == 16 && dow == 4) return true;  // 16h/Thu
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| VOLATILITY FILTER (ATR on H1)                                     |
//+------------------------------------------------------------------+
bool IsVolatilityOK() {
   double atr = iATR(Symbol(), r_TrendTF, ATR_Period, 0);
   double atrPips = atr / g_pipValue;

   // Too calm — no momentum for pullback
   if(atrPips < r_ATR_MinPips) return false;

   // Too volatile — pullbacks become retournements
   if(r_ATR_MaxPips > 0 && atrPips > r_ATR_MaxPips) return false;

   return true;
}

//+------------------------------------------------------------------+
//| EMA50 DISTANCE FILTER — reject overextended entries              |
//| Winners avg 23 pips from EMA50, Losers avg 35 pips              |
//+------------------------------------------------------------------+
bool IsEMA50DistanceOK() {
   if(!UseEMA50DistFilter) return true;

   double ema50 = iMA(Symbol(), r_TrendTF, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
   double price = (MarketInfo(Symbol(), MODE_BID) + MarketInfo(Symbol(), MODE_ASK)) / 2.0;
   double distPips = MathAbs(price - ema50) / g_pipValue;

   if(distPips > r_MaxEMA50DistPips) return false;

   return true;
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
//| GET H1 TREND DIRECTION                                            |
//| Returns: 1 = bullish, -1 = bearish, 0 = no trend                 |
//+------------------------------------------------------------------+
int GetTrendDirection() {
   double ema_now  = iMA(Symbol(), r_TrendTF, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
   double ema_prev = iMA(Symbol(), r_TrendTF, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, r_TrendBars);
   double close_tf = iClose(Symbol(), r_TrendTF, 0);

   // Bullish: price above EMA AND EMA rising
   if(close_tf > ema_now && ema_now > ema_prev)
      return 1;

   // Bearish: price below EMA AND EMA falling
   if(close_tf < ema_now && ema_now < ema_prev)
      return -1;

   return 0;
}

//+------------------------------------------------------------------+
//| CHECK FOR PULLBACK ENTRY ON M15                                   |
//+------------------------------------------------------------------+
void CheckEntry() {
   int trend = GetTrendDirection();
   if(trend == 0) return;

   double ema20 = iMA(Symbol(), r_EntryTF, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);

   // Last closed bar (bar 1)
   double open1  = iOpen(Symbol(), r_EntryTF, 1);
   double close1 = iClose(Symbol(), r_EntryTF, 1);
   double high1  = iHigh(Symbol(), r_EntryTF, 1);
   double low1   = iLow(Symbol(), r_EntryTF, 1);

   // Previous bar (bar 2) — must have touched/crossed EMA
   double open2  = iOpen(Symbol(), r_EntryTF, 2);
   double close2 = iClose(Symbol(), r_EntryTF, 2);
   double low2   = iLow(Symbol(), r_EntryTF, 2);
   double high2  = iHigh(Symbol(), r_EntryTF, 2);

   // Price action: body sizes
   double body1  = MathAbs(close1 - open1);
   double range1 = high1 - low1;
   double body2  = MathAbs(close2 - open2);

   double bid = MarketInfo(Symbol(), MODE_BID);
   double ask = MarketInfo(Symbol(), MODE_ASK);

   // RSI filter
   double rsi = iRSI(Symbol(), r_EntryTF, RSI_Period, PRICE_CLOSE, 1);

   // ============ BULLISH PULLBACK ============
   if(trend == 1) {
      if(rsi > RSI_OB) return;  // Don't buy when overbought
      // Bar 2 must have dipped to or below EMA20 (pullback)
      double ema20_bar2 = iMA(Symbol(), r_EntryTF, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
      if(low2 > ema20_bar2) return;  // No pullback to EMA

      // Bar 1 must close above EMA20 (rejection/bounce)
      if(close1 <= ema20) return;
      // Bar 1 must be bullish
      if(close1 <= open1) return;
      // Price action: strong body (>60% of range) and stronger than pullback bar
      if(range1 > 0 && body1 / range1 < 0.6) return;
      if(body1 <= body2) return;

      // Calculate SL: lowest low of last r_SL_SwingBars bars
      double sl = low1;
      for(int i = 1; i <= r_SL_SwingBars; i++) {
         double l = iLow(Symbol(), r_EntryTF, i);
         if(l < sl) sl = l;
      }
      sl = sl - 2 * g_pipValue;  // Buffer

      double slDist = (ask - sl) / g_pipValue;
      if(slDist < r_MinSL_Pips || slDist > r_MaxSL_Pips) return;

      double tp = ask + (ask - sl) * r_MinRR;

      ExecuteTrade(OP_BUY, ask, sl, tp, "EMA Pullback Buy");
   }

   // ============ BEARISH PULLBACK ============
   if(trend == -1) {
      if(rsi < RSI_OS) return;  // Don't sell when oversold
      // Bar 2 must have spiked to or above EMA20 (pullback)
      double ema20_bar2 = iMA(Symbol(), r_EntryTF, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
      if(high2 < ema20_bar2) return;  // No pullback to EMA

      // Bar 1 must close below EMA20 (rejection)
      if(close1 >= ema20) return;
      // Bar 1 must be bearish
      if(close1 >= open1) return;
      // Price action: strong body (>60% of range) and stronger than pullback bar
      if(range1 > 0 && body1 / range1 < 0.6) return;
      if(body1 <= body2) return;

      // Calculate SL: highest high of last r_SL_SwingBars bars
      double sl = high1;
      for(int i = 1; i <= r_SL_SwingBars; i++) {
         double h = iHigh(Symbol(), r_EntryTF, i);
         if(h > sl) sl = h;
      }
      sl = sl + 2 * g_pipValue;  // Buffer

      double slDist = (sl - bid) / g_pipValue;
      if(slDist < r_MinSL_Pips || slDist > r_MaxSL_Pips) return;

      double tp = bid - (sl - bid) * r_MinRR;

      ExecuteTrade(OP_SELL, bid, sl, tp, "EMA Pullback Sell");
   }
}

//+------------------------------------------------------------------+
//| EXECUTE TRADE                                                     |
//+------------------------------------------------------------------+
void ExecuteTrade(int type, double price, double sl, double tp, string comment) {
   double slDist = MathAbs(price - sl);

   // Reduce risk on Thursday (weakest day PF=1.08)
   double riskMult = 1.0;
   if(r_ReduceThursdayRisk && TimeDayOfWeek(TimeCurrent()) == 4) {
      riskMult = r_ThursdayRiskMult;
      comment = comment + "|THU_REDUCED";
   }

   double lotSize = CalculateLotSize(slDist, riskMult);

   if(lotSize <= 0) {
      Print("Lot size invalid: ", lotSize);
      return;
   }

   price = NormalizeDouble(price, g_digits);
   sl    = NormalizeDouble(sl, g_digits);
   tp    = NormalizeDouble(tp, g_digits);

   // Store initial risk in comment
   string fullComment = comment + "|R=" + DoubleToStr(slDist, g_digits);

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
      g_dailyTrades++;
      Print("Trade opened #", ticket,
            " | ", comment,
            " | Lots: ", lotSize,
            " | SL: ", sl,
            " | TP: ", tp,
            " | RR: ", DoubleToStr(MathAbs(tp - price) / slDist, 1));
   }
}

//+------------------------------------------------------------------+
//| CALCULATE LOT SIZE (Risk-based)                                  |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistance, double riskMultiplier = 1.0) {
   if(slDistance <= 0) return 0;

   double riskMoney = AccountBalance() * RiskPercent / 100.0 * riskMultiplier;
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
//| MANAGE OPEN TRADES (Breakeven)                                   |
//+------------------------------------------------------------------+
void ManageOpenTrades() {
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();

      // Get initial risk from comment
      string comment = OrderComment();
      double riskDist = GetInitialRisk(comment, MathAbs(openPrice - currentSL));
      if(riskDist <= 0) continue;

      if(OrderType() == OP_BUY) {
         double currentPrice = MarketInfo(Symbol(), MODE_BID);
         double profit = currentPrice - openPrice;

         // Breakeven at BE_Trigger_R (default 1.5R — gives trade more room)
         if(UseBreakeven && profit >= riskDist * r_BE_Trigger_R && currentSL < openPrice) {
            double beSL = openPrice + 1 * g_pipValue;
            if(!OrderModify(OrderTicket(), openPrice, NormalizeDouble(beSL, g_digits),
                           OrderTakeProfit(), 0, clrYellow))
               Print("BE modify failed: ", GetLastError());
         }
      }
      else if(OrderType() == OP_SELL) {
         double currentPrice = MarketInfo(Symbol(), MODE_ASK);
         double profit = openPrice - currentPrice;

         // Breakeven at BE_Trigger_R
         if(UseBreakeven && profit >= riskDist * r_BE_Trigger_R && currentSL > openPrice) {
            double beSL = openPrice - 1 * g_pipValue;
            if(!OrderModify(OrderTicket(), openPrice, NormalizeDouble(beSL, g_digits),
                           OrderTakeProfit(), 0, clrYellow))
               Print("BE modify failed: ", GetLastError());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| GET INITIAL RISK from order comment                              |
//+------------------------------------------------------------------+
double GetInitialRisk(string comment, double fallback) {
   int pos = StringFind(comment, "|R=");
   if(pos < 0) return fallback;
   string rStr = StringSubstr(comment, pos + 3);
   double r = StringToDouble(rStr);
   return (r > 0) ? r : fallback;
}
//+------------------------------------------------------------------+
