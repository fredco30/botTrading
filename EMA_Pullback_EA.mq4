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
// --- Risk Management ---
input double RiskPercent        = 1.0;     // Risk % per trade
input double MaxSpreadPips      = 3.0;     // Max spread allowed (pips)
input int    MagicNumber        = 20250407;// Magic number
input double MinRR              = 2.5;     // Minimum Risk:Reward ratio
input double MinSL_Pips         = 10.0;    // Minimum SL distance (pips)
input double MaxSL_Pips         = 30.0;    // Maximum SL distance (pips)

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
input double ATR_MinPips         = 6.0;    // Min ATR in pips to allow trading

// --- Day/Hour Filters ---
input bool   BlockFriday         = true;   // Do not trade on Friday
input bool   BlockHour13         = true;   // Do not trade at 13:00 (NY open chaos)
input string BlockedHours        = "13";   // Comma-separated hours to block (server time)

//+------------------------------------------------------------------+
//| GLOBALS                                                           |
//+------------------------------------------------------------------+
double     g_pipValue;
int        g_digits;
datetime   g_lastBarTime = 0;
datetime   g_currentDay  = 0;
int        g_dailyTrades = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   if(g_digits == 3 || g_digits == 5)
      g_pipValue = Point * 10;
   else
      g_pipValue = Point;

   Print("EMA Pullback EA initialized | Symbol: ", Symbol(),
         " | Pip value: ", g_pipValue,
         " | H1 EMA: ", TrendEMA_Period,
         " | M15 EMA: ", EntryEMA_Period,
         " | ATR filter: ", UseATRFilter ? "ON (min " + DoubleToStr(ATR_MinPips, 1) + " pips)" : "OFF",
         " | Friday: ", BlockFriday ? "BLOCKED" : "allowed",
         " | BE trigger: ", DoubleToStr(BE_Trigger_R, 1), "R");
   return INIT_SUCCEEDED;
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

   // --- New bar check (M15) ---
   datetime currentBarTime = iTime(Symbol(), PERIOD_M15, 0);
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
   if(CountOpenTrades() >= 1) return;
   if(g_dailyTrades >= MaxTradesPerDay) return;

   // --- Check for entry ---
   CheckEntry();
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
//| DAY FILTER (block Friday)                                         |
//+------------------------------------------------------------------+
bool IsDayBlocked() {
   int dow = TimeDayOfWeek(TimeCurrent());
   if(BlockFriday && dow == 5) return true;
   return false;
}

//+------------------------------------------------------------------+
//| HOUR FILTER (block toxic hours)                                   |
//+------------------------------------------------------------------+
bool IsHourBlocked() {
   int hour = TimeHour(TimeCurrent());

   // Quick check for the main blocked hour
   if(BlockHour13 && hour == 13) return true;

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
   return false;
}

//+------------------------------------------------------------------+
//| VOLATILITY FILTER (ATR on H1)                                     |
//+------------------------------------------------------------------+
bool IsVolatilityOK() {
   double atr = iATR(Symbol(), PERIOD_H1, ATR_Period, 0);
   double atrPips = atr / g_pipValue;

   if(atrPips < ATR_MinPips) {
      // Silent filter — only print when we would have traded
      return false;
   }
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
   double ema_now  = iMA(Symbol(), PERIOD_H1, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
   double ema_prev = iMA(Symbol(), PERIOD_H1, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, TrendBars);
   double close_h1 = iClose(Symbol(), PERIOD_H1, 0);

   // Bullish: price above EMA AND EMA rising
   if(close_h1 > ema_now && ema_now > ema_prev)
      return 1;

   // Bearish: price below EMA AND EMA falling
   if(close_h1 < ema_now && ema_now < ema_prev)
      return -1;

   return 0;
}

//+------------------------------------------------------------------+
//| CHECK FOR PULLBACK ENTRY ON M15                                   |
//+------------------------------------------------------------------+
void CheckEntry() {
   int trend = GetTrendDirection();
   if(trend == 0) return;

   double ema20 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);

   // Last closed bar (bar 1)
   double open1  = iOpen(Symbol(), PERIOD_M15, 1);
   double close1 = iClose(Symbol(), PERIOD_M15, 1);
   double high1  = iHigh(Symbol(), PERIOD_M15, 1);
   double low1   = iLow(Symbol(), PERIOD_M15, 1);

   // Previous bar (bar 2) — must have touched/crossed EMA
   double open2  = iOpen(Symbol(), PERIOD_M15, 2);
   double close2 = iClose(Symbol(), PERIOD_M15, 2);
   double low2   = iLow(Symbol(), PERIOD_M15, 2);
   double high2  = iHigh(Symbol(), PERIOD_M15, 2);

   // Price action: body sizes
   double body1  = MathAbs(close1 - open1);
   double range1 = high1 - low1;
   double body2  = MathAbs(close2 - open2);

   double bid = MarketInfo(Symbol(), MODE_BID);
   double ask = MarketInfo(Symbol(), MODE_ASK);

   // RSI filter
   double rsi = iRSI(Symbol(), PERIOD_M15, RSI_Period, PRICE_CLOSE, 1);

   // ============ BULLISH PULLBACK ============
   if(trend == 1) {
      if(rsi > RSI_OB) return;  // Don't buy when overbought
      // Bar 2 must have dipped to or below EMA20 (pullback)
      double ema20_bar2 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
      if(low2 > ema20_bar2) return;  // No pullback to EMA

      // Bar 1 must close above EMA20 (rejection/bounce)
      if(close1 <= ema20) return;
      // Bar 1 must be bullish
      if(close1 <= open1) return;
      // Price action: strong body (>60% of range) and stronger than pullback bar
      if(range1 > 0 && body1 / range1 < 0.6) return;
      if(body1 <= body2) return;

      // Calculate SL: lowest low of last SL_SwingBars bars
      double sl = low1;
      for(int i = 1; i <= SL_SwingBars; i++) {
         double l = iLow(Symbol(), PERIOD_M15, i);
         if(l < sl) sl = l;
      }
      sl = sl - 2 * g_pipValue;  // Buffer

      double slDist = (ask - sl) / g_pipValue;
      if(slDist < MinSL_Pips || slDist > MaxSL_Pips) return;

      double tp = ask + (ask - sl) * MinRR;

      ExecuteTrade(OP_BUY, ask, sl, tp, "EMA Pullback Buy");
   }

   // ============ BEARISH PULLBACK ============
   if(trend == -1) {
      if(rsi < RSI_OS) return;  // Don't sell when oversold
      // Bar 2 must have spiked to or above EMA20 (pullback)
      double ema20_bar2 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
      if(high2 < ema20_bar2) return;  // No pullback to EMA

      // Bar 1 must close below EMA20 (rejection)
      if(close1 >= ema20) return;
      // Bar 1 must be bearish
      if(close1 >= open1) return;
      // Price action: strong body (>60% of range) and stronger than pullback bar
      if(range1 > 0 && body1 / range1 < 0.6) return;
      if(body1 <= body2) return;

      // Calculate SL: highest high of last SL_SwingBars bars
      double sl = high1;
      for(int i = 1; i <= SL_SwingBars; i++) {
         double h = iHigh(Symbol(), PERIOD_M15, i);
         if(h > sl) sl = h;
      }
      sl = sl + 2 * g_pipValue;  // Buffer

      double slDist = (sl - bid) / g_pipValue;
      if(slDist < MinSL_Pips || slDist > MaxSL_Pips) return;

      double tp = bid - (sl - bid) * MinRR;

      ExecuteTrade(OP_SELL, bid, sl, tp, "EMA Pullback Sell");
   }
}

//+------------------------------------------------------------------+
//| EXECUTE TRADE                                                     |
//+------------------------------------------------------------------+
void ExecuteTrade(int type, double price, double sl, double tp, string comment) {
   double slDist = MathAbs(price - sl);
   double lotSize = CalculateLotSize(slDist);

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
         if(UseBreakeven && profit >= riskDist * BE_Trigger_R && currentSL < openPrice) {
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
         if(UseBreakeven && profit >= riskDist * BE_Trigger_R && currentSL > openPrice) {
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
