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
input double TP1_RR             = 2.0;     // TP1 partial close at X * Risk
input double TP1_ClosePercent   = 50.0;    // % of lots to close at TP1
input double TrailBuffer_Pips   = 2.0;     // Trailing SL buffer from EMA (pips)
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
input int    MaxTradesPerDay    = 2;       // Max trades per day

//+------------------------------------------------------------------+
//| GLOBALS                                                           |
//+------------------------------------------------------------------+
double     g_pipValue;
int        g_digits;
datetime   g_lastBarTime = 0;
bool       g_tp1Fired    = false;
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
         " | M15 EMA: ", EntryEMA_Period);
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

      ExecuteTrade(OP_BUY, ask, sl, 0, "EMA Pullback Buy");
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

      ExecuteTrade(OP_SELL, bid, sl, 0, "EMA Pullback Sell");
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
//| MANAGE OPEN TRADES (TP1 partial close + EMA trailing)            |
//+------------------------------------------------------------------+
void ManageOpenTrades() {
   // Reset TP1 flag if no trades open
   if(CountOpenTrades() == 0) {
      g_tp1Fired = false;
      return;
   }

   double minDist = MarketInfo(Symbol(), MODE_STOPLEVEL) * Point;

   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      string comment   = OrderComment();
      double riskDist  = GetInitialRisk(comment, MathAbs(openPrice - currentSL));
      if(riskDist <= 0) continue;

      bool isRemainder = g_tp1Fired || (StringFind(comment, "from #") >= 0);

      // ===================== BUY =====================
      if(OrderType() == OP_BUY) {
         double currentPrice = MarketInfo(Symbol(), MODE_BID);
         double profit = currentPrice - openPrice;

         // --- Phase 1: TP1 partial close at TP1_RR ---
         if(!isRemainder && profit >= TP1_RR * riskDist && currentSL < openPrice) {
            double closeLots = CalcPartialLots(OrderLots());
            if(closeLots >= MarketInfo(Symbol(), MODE_MINLOT)) {
               if(OrderClose(OrderTicket(), closeLots, currentPrice, 3, clrYellow)) {
                  g_tp1Fired = true;
                  Print("TP1 hit: closed ", closeLots, " lots at +",
                        DoubleToStr(profit / g_pipValue, 1), " pips");
                  SetBreakevenOnRemaining(OP_BUY, openPrice);
                  return; // Order list changed
               }
               else Print("TP1 close failed: ", GetLastError());
            }
         }

         // --- Set BE on remainder if not yet done ---
         if(isRemainder && currentSL < openPrice) {
            double beSL = NormalizeDouble(openPrice + 1 * g_pipValue, g_digits);
            if(!OrderModify(OrderTicket(), openPrice, beSL, OrderTakeProfit(), 0, clrYellow))
               Print("BE modify failed: ", GetLastError());
         }

         // --- Phase 2: Trailing EMA20 M15 ---
         if(currentSL >= openPrice) {
            double ema20 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
            double newSL = NormalizeDouble(ema20 - TrailBuffer_Pips * g_pipValue, g_digits);
            if(newSL > currentSL + 0.5 * g_pipValue && currentPrice - newSL > minDist) {
               if(!OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrAqua))
                  Print("Trail SL failed: ", GetLastError());
               else
                  Print("Trail SL → ", newSL, " (EMA20=", DoubleToStr(ema20, g_digits), ")");
            }
         }
      }

      // ===================== SELL =====================
      else if(OrderType() == OP_SELL) {
         double currentPrice = MarketInfo(Symbol(), MODE_ASK);
         double profit = openPrice - currentPrice;

         // --- Phase 1: TP1 partial close at TP1_RR ---
         if(!isRemainder && profit >= TP1_RR * riskDist && currentSL > openPrice) {
            double closeLots = CalcPartialLots(OrderLots());
            if(closeLots >= MarketInfo(Symbol(), MODE_MINLOT)) {
               if(OrderClose(OrderTicket(), closeLots, currentPrice, 3, clrYellow)) {
                  g_tp1Fired = true;
                  Print("TP1 hit: closed ", closeLots, " lots at +",
                        DoubleToStr(profit / g_pipValue, 1), " pips");
                  SetBreakevenOnRemaining(OP_SELL, openPrice);
                  return;
               }
               else Print("TP1 close failed: ", GetLastError());
            }
         }

         // --- Set BE on remainder if not yet done ---
         if(isRemainder && currentSL > openPrice) {
            double beSL = NormalizeDouble(openPrice - 1 * g_pipValue, g_digits);
            if(!OrderModify(OrderTicket(), openPrice, beSL, OrderTakeProfit(), 0, clrYellow))
               Print("BE modify failed: ", GetLastError());
         }

         // --- Phase 2: Trailing EMA20 M15 ---
         if(currentSL > 0 && currentSL <= openPrice) {
            double ema20 = iMA(Symbol(), PERIOD_M15, EntryEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
            double newSL = NormalizeDouble(ema20 + TrailBuffer_Pips * g_pipValue, g_digits);
            if(newSL < currentSL - 0.5 * g_pipValue && newSL - currentPrice > minDist) {
               if(!OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrAqua))
                  Print("Trail SL failed: ", GetLastError());
               else
                  Print("Trail SL → ", newSL, " (EMA20=", DoubleToStr(ema20, g_digits), ")");
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| CALC PARTIAL LOTS for TP1                                        |
//+------------------------------------------------------------------+
double CalcPartialLots(double totalLots) {
   double closeLots = totalLots * TP1_ClosePercent / 100.0;
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);
   closeLots = MathFloor(closeLots / lotStep) * lotStep;
   closeLots = NormalizeDouble(closeLots, 2);
   // If can't split, close everything
   if(closeLots < MarketInfo(Symbol(), MODE_MINLOT))
      closeLots = totalLots;
   return closeLots;
}

//+------------------------------------------------------------------+
//| SET BREAKEVEN on remaining position after partial close           |
//+------------------------------------------------------------------+
void SetBreakevenOnRemaining(int type, double openPrice) {
   for(int j = OrdersTotal() - 1; j >= 0; j--) {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      if(OrderType() != type) continue;

      double beSL;
      if(type == OP_BUY)
         beSL = openPrice + 1 * g_pipValue;
      else
         beSL = openPrice - 1 * g_pipValue;

      beSL = NormalizeDouble(beSL, g_digits);
      if(!OrderModify(OrderTicket(), OrderOpenPrice(), beSL, OrderTakeProfit(), 0, clrYellow))
         Print("BE after TP1 failed: ", GetLastError());
      else
         Print("BE set on remaining position at ", beSL);
      break;
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
