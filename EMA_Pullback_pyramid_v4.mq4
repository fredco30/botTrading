//+------------------------------------------------------------------+
//|                                 EMA_Pullback_pyramid_v4.mq4      |
//|            EMA Pullback Trend Following + Anti-Martingale Pyramid |
//|                    H1 Trend + M15 Pullback Entry                   |
//|         + Reverse Trade + State Persistence + DD Kill-Switch       |
//|                                                                    |
//|  v4.00: optimized config (Python 16y backtest 2010-2026) +         |
//|         pyramid-state persistence across restarts + hard DD stop.  |
//|                                                                    |
//|  Backtest (Python M15-bar approx, EURUSD 2010-2026, $10k):        |
//|    Net +$407k / Max DD 37% / PF 1.83 / 2 negative years (2010,2021)|
//|  WARNING: re-validate in MT4 Strategy Tester before any live use.  |
//|  Recommended capital >= $25k (DD drops to ~21%).                   |
//+------------------------------------------------------------------+
#property copyright "EMA Pullback Pyramid EA v4.00"
#property link      ""
#property version   "4.00"
#property strict

//+------------------------------------------------------------------+
//| INPUTS (champion config from Python optimization)                |
//+------------------------------------------------------------------+
// --- Risk Management ---
input double RiskPercent        = 1.5;     // Risk % per trade (champion: 1.5)
input double MaxSpreadPips      = 3.0;     // Max spread allowed (pips)
input int    MagicNumber        = 20260723;// Magic number (v4)
input double MinRR              = 2.0;     // Minimum Risk:Reward ratio
input double MinSL_Pips         = 15.0;    // Minimum SL distance (pips)
input double MaxSL_Pips         = 25.0;    // Maximum SL distance (pips)

// --- Hard kill-switch (drawdown) ---
input bool   UseKillSwitch      = true;    // Stop EA when DD exceeds limit
input double MaxDDPercent       = 40.0;    // Total DD% -> halt all trading
input double DailyDDPercent     = 5.0;     // Daily DD% -> stop for the day

// --- ANTI-MARTINGALE PYRAMID (on wins) ---
enum PYRAMID_MODE {
   MODE_SAFE       = 0,   // SAFE: L0=1.0 L1=4.0 L2=2.5 (legacy)
   MODE_AGGRESSIVE = 1,   // AGGRESSIVE: L0=2.0 L1=7.0 L2=4.0 (legacy)
   MODE_CUSTOM     = 2    // CUSTOM: use L0/L1/L2 inputs (champion default)
};
input bool         UsePyramid    = true;        // enable pyramid lot sizing
input PYRAMID_MODE PyramidMode   = MODE_CUSTOM; // preset mode
input double       L0_LotMult    = 0.25;        // L0 mult (champion: 0.25)
input double       L1_LotMult    = 6.0;         // L1 mult (champion: 6.0)
input double       L2_LotMult    = 3.0;         // L2 mult (champion: 3.0)
input int          MaxStreakLevel = 2;          // streak cap (L0,L1,L2)

// --- Reverse Trade (on SL) ---
input bool         UseReverseTrade = true;      // reverse when trade hits SL
input bool         UseReverseOnL0  = true;      // reverse on L0 SL
input bool         UseReverseOnL2  = true;      // reverse on L2 SL (when cold)
input bool         UseRevLotFromLevel = true;   // reverse lot = losing level lot
input double       RevLotMult      = 1.0;       // reverse lot mult (if not from level)
input double       RevMaxSL_Pips   = 20.0;      // max reverse SL (champion: 20)
input int          RevMinConsecLosses = 3;      // reverse L0 after N consec losses

// --- Signal Health (Rolling WR) ---
input int          RollingWR_Window  = 5;       // last N L0 trades for WR
input double       RollingWR_Threshold = 25.0;  // below -> signal cold (champion: 25)

// --- Trend Filter (H1) ---
input int    TrendEMA_Period    = 50;      // H1 EMA period
input int    TrendBars          = 5;       // EMA slope bars

// --- Entry (M15) ---
input int    EntryEMA_Period    = 20;      // M15 EMA period
input int    SL_SwingBars       = 2;       // swing lookback for SL (champion: 2)
input int    RSI_Period         = 14;      // RSI period
input int    RSI_OB             = 70;      // RSI overbought
input int    RSI_OS             = 30;      // RSI oversold

// --- Session Filter ---
input int    LondonStartHour    = 8;       // London start
input int    LondonEndHour      = 11;      // London end (champion: 11)
input int    NYStartHour        = 13;      // NY start
input int    NYEndHour          = 18;      // NY end (champion: 18)

// --- Trade Management ---
input bool   UseBreakeven       = true;    // move SL to BE
input double BE_Trigger_R       = 2.0;     // BE after X*R (champion: 2.0)
input int    MaxTradesPerDay    = 3;       // max trades/day (champion: 3)

// --- Volatility Filter (ATR H1) ---
input bool   UseATRFilter       = true;    // ATR band filter
input int    ATR_Period         = 14;      // ATR period
input double ATR_MinPips        = 7.0;     // min ATR (champion: 7) - DO NOT raise to 9
input double ATR_MaxPips        = 19.0;    // max ATR (champion: 19) - DO NOT lower to 17

// --- EMA50 Distance Filter ---
input bool   UseEMA50DistFilter = true;    // block far-from-EMA50 entries
input double MaxEMA50DistPips   = 30.0;    // max dist (champion: 30) - DO NOT raise

// --- Pullback/Structure filters (kept OFF, tested) ---
input bool   UsePullbackSizeFilter = false;
input double PB_MaxRatio         = 0.70;
input bool   UseStructureFilter  = false;
input int    StructureSwingBars  = 5;

// --- Day/Hour Filters ---
input bool   BlockFriday        = true;
input bool   BlockHour13        = true;
input string BlockedHours       = "13";
input bool   BlockToxicCombos   = true;
input bool   ReduceThursdayRisk = true;
input double ThursdayRiskMult   = 0.5;

// --- Persistence ---
input bool   UsePersistence     = true;    // save pyramid state across restarts

//+------------------------------------------------------------------+
//| GLOBALS                                                           |
//+------------------------------------------------------------------+
double     g_pipValue;
int        g_digits;
datetime   g_lastBarTime = 0;
datetime   g_currentDay  = 0;
int        g_dailyTrades = 0;
double     g_dayStartBalance = 0.0;
bool       g_halted = false;      // kill-switch total halt
double     g_equityPeak = 0.0;    // for DD tracking

struct PyramidState {
   int    streak;
   int    lastTicket;
   bool   waitingForClose;
   int    lastTradeLevel;
   bool   lastTradeIsReverse;
   int    lastTradeType;
   int    consecLosses;
};
PyramidState g_pyr;

int g_rollingL0[20];
int g_rollingL0_count = 0;
int g_rollingL0_index = 0;

double r_L0_LotMult = 0.25;
double r_L1_LotMult = 6.0;
double r_L2_LotMult = 3.0;

double  r_MinRR, r_MinSL_Pips, r_MaxSL_Pips, r_ATR_MinPips, r_ATR_MaxPips;
double  r_MaxEMA50DistPips, r_BE_Trigger_R, r_ThursdayRiskMult;
int     r_LondonStartHour, r_LondonEndHour, r_NYStartHour, r_NYEndHour;
int     r_MaxTradesPerDay, r_TrendBars, r_SL_SwingBars;
bool    r_BlockFriday, r_BlockToxicCombos, r_ReduceThursdayRisk;
int     r_BlockedHoursArr[10];
int     r_BlockedHoursCount;

string GV_PREFIX;

//+------------------------------------------------------------------+
void ApplyPyramidMode() {
   if(PyramidMode == MODE_SAFE)      { r_L0_LotMult=1.0; r_L1_LotMult=4.0; r_L2_LotMult=2.5; }
   else if(PyramidMode == MODE_AGGRESSIVE){ r_L0_LotMult=2.0; r_L1_LotMult=7.0; r_L2_LotMult=4.0; }
   else { r_L0_LotMult=L0_LotMult; r_L1_LotMult=L1_LotMult; r_L2_LotMult=L2_LotMult; }
}

//+------------------------------------------------------------------+
//| PERSISTENCE (GlobalVariables, keyed by symbol+magic)             |
//+------------------------------------------------------------------+
void SaveState() {
   if(!UsePersistence) return;
   GlobalVariableSet(GV_PREFIX+"streak", g_pyr.streak);
   GlobalVariableSet(GV_PREFIX+"consec", g_pyr.consecLosses);
   GlobalVariableSet(GV_PREFIX+"ticket", g_pyr.lastTicket);
   GlobalVariableSet(GV_PREFIX+"waiting", g_pyr.waitingForClose ? 1:0);
   GlobalVariableSet(GV_PREFIX+"lvl", g_pyr.lastTradeLevel);
   GlobalVariableSet(GV_PREFIX+"isrev", g_pyr.lastTradeIsReverse ? 1:0);
   GlobalVariableSet(GV_PREFIX+"type", g_pyr.lastTradeType);
   GlobalVariableSet(GV_PREFIX+"rcount", g_rollingL0_count);
   GlobalVariableSet(GV_PREFIX+"ridx", g_rollingL0_index);
   GlobalVariableSet(GV_PREFIX+"peak", g_equityPeak);
   for(int i=0;i<20;i++)
      GlobalVariableSet(GV_PREFIX+"roll"+IntegerToString(i), g_rollingL0[i]);
}

void LoadState() {
   if(!UsePersistence) return;
   if(!GlobalVariableCheck(GV_PREFIX+"streak")) return;  // no prior state
   g_pyr.streak           = (int)GlobalVariableGet(GV_PREFIX+"streak");
   g_pyr.consecLosses     = (int)GlobalVariableGet(GV_PREFIX+"consec");
   g_pyr.lastTicket       = (int)GlobalVariableGet(GV_PREFIX+"ticket");
   g_pyr.waitingForClose  = GlobalVariableGet(GV_PREFIX+"waiting") > 0.5;
   g_pyr.lastTradeLevel   = (int)GlobalVariableGet(GV_PREFIX+"lvl");
   g_pyr.lastTradeIsReverse = GlobalVariableGet(GV_PREFIX+"isrev") > 0.5;
   g_pyr.lastTradeType    = (int)GlobalVariableGet(GV_PREFIX+"type");
   g_rollingL0_count      = (int)GlobalVariableGet(GV_PREFIX+"rcount");
   g_rollingL0_index      = (int)GlobalVariableGet(GV_PREFIX+"ridx");
   g_equityPeak           = GlobalVariableGet(GV_PREFIX+"peak");
   for(int i=0;i<20;i++)
      g_rollingL0[i] = (int)GlobalVariableGet(GV_PREFIX+"roll"+IntegerToString(i));
   Print("STATE RESTORED: streak=", g_pyr.streak,
         " consec=", g_pyr.consecLosses,
         " ticket=", g_pyr.lastTicket,
         " waiting=", g_pyr.waitingForClose);
}

//+------------------------------------------------------------------+
int OnInit() {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   g_pipValue = (g_digits==3 || g_digits==5) ? Point*10 : Point;

   GV_PREFIX = "EMP4_" + Symbol() + "_" + IntegerToString(MagicNumber) + "_";

   ApplyPreset();
   ApplyPyramidMode();

   g_pyr.streak=0; g_pyr.lastTicket=0; g_pyr.waitingForClose=false;
   g_pyr.lastTradeLevel=0; g_pyr.lastTradeIsReverse=false; g_pyr.lastTradeType=-1;
   g_pyr.consecLosses=0;
   g_rollingL0_count=0; g_rollingL0_index=0;
   ArrayInitialize(g_rollingL0,0);
   g_equityPeak = AccountBalance();
   g_halted = false;

   LoadState();  // restore pyramid state if present
   if(g_equityPeak < AccountBalance()) g_equityPeak = AccountBalance();

   Print("EMA Pullback Pyramid v4 initialized | ", Symbol(),
         " | L0:", DoubleToStr(r_L0_LotMult,2),
         " L1:", DoubleToStr(r_L1_LotMult,2),
         " L2:", DoubleToStr(r_L2_LotMult,2),
         " | Risk:", DoubleToStr(RiskPercent,2), "%",
         " | KillSwitch:", UseKillSwitch ? "ON":"OFF",
         " | Persistence:", UsePersistence ? "ON":"OFF");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void ApplyPreset() {
   r_MinRR=MinRR; r_MinSL_Pips=MinSL_Pips; r_MaxSL_Pips=MaxSL_Pips;
   r_ATR_MinPips=ATR_MinPips; r_ATR_MaxPips=ATR_MaxPips;
   r_MaxEMA50DistPips=MaxEMA50DistPips; r_BE_Trigger_R=BE_Trigger_R;
   r_LondonStartHour=LondonStartHour; r_LondonEndHour=LondonEndHour;
   r_NYStartHour=NYStartHour; r_NYEndHour=NYEndHour;
   r_BlockFriday=BlockFriday; r_BlockToxicCombos=BlockToxicCombos;
   r_ReduceThursdayRisk=ReduceThursdayRisk; r_ThursdayRiskMult=ThursdayRiskMult;
   r_MaxTradesPerDay=MaxTradesPerDay; r_TrendBars=TrendBars; r_SL_SwingBars=SL_SwingBars;
   r_BlockedHoursCount=1; r_BlockedHoursArr[0]=13;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   SaveState();
   Print("EMA Pullback Pyramid v4 removed. Reason: ", reason, " (state saved)");
}

//+------------------------------------------------------------------+
//| KILL-SWITCH: halt on total DD, stop-for-day on daily DD          |
//+------------------------------------------------------------------+
bool KillSwitchHalted() {
   if(!UseKillSwitch) return false;
   double eq = AccountEquity();
   if(eq > g_equityPeak) g_equityPeak = eq;
   if(g_equityPeak <= 0) return false;
   double ddPct = (g_equityPeak - eq) / g_equityPeak * 100.0;
   if(ddPct >= MaxDDPercent) {
      if(!g_halted)
         Print("KILL-SWITCH TRIGGERED: DD ", DoubleToStr(ddPct,1), "% >= ",
               DoubleToStr(MaxDDPercent,1), "%. EA halted.");
      g_halted = true;
   }
   return g_halted;
}

bool DailyLimitHit() {
   if(!UseKillSwitch) return false;
   if(g_dayStartBalance <= 0) return false;
   double eq = AccountEquity();
   double dayDD = (g_dayStartBalance - eq) / g_dayStartBalance * 100.0;
   if(dayDD >= DailyDDPercent) return true;
   return false;
}

//+------------------------------------------------------------------+
void OnTick() {
   ManageOpenTrades();
   CheckPyramidClose();

   if(KillSwitchHalted()) return;

   datetime currentBarTime = iTime(Symbol(), PERIOD_M15, 0);
   if(currentBarTime == g_lastBarTime) return;
   g_lastBarTime = currentBarTime;

   datetime today = TimeCurrent() - TimeCurrent() % 86400;
   if(today != g_currentDay) {
      g_dailyTrades = 0;
      g_currentDay = today;
      g_dayStartBalance = AccountBalance();
   }

   if(DailyLimitHit()) return;
   if(!IsSessionActive()) return;
   if(SpreadTooWide()) return;
   if(IsDayBlocked()) return;
   if(IsHourBlocked()) return;
   if(UseATRFilter && !IsVolatilityOK()) return;
   if(!IsEMA50DistanceOK()) return;
   if(CountOpenTrades() >= 1) return;
   if(g_dailyTrades >= r_MaxTradesPerDay) return;

   CheckEntry();
}

//+------------------------------------------------------------------+
bool IsSessionActive() {
   int hour = TimeHour(TimeCurrent());
   if(hour >= r_LondonStartHour && hour < r_LondonEndHour) return true;
   if(hour >= r_NYStartHour && hour < r_NYEndHour) return true;
   return false;
}

bool SpreadTooWide() {
   double spread = MarketInfo(Symbol(), MODE_SPREAD) * Point / g_pipValue;
   return (spread > MaxSpreadPips);
}

bool IsDayBlocked() {
   int dow = TimeDayOfWeek(TimeCurrent());
   if(r_BlockFriday && dow == 5) return true;
   return false;
}

bool IsHourBlocked() {
   int hour = TimeHour(TimeCurrent());
   int dow  = TimeDayOfWeek(TimeCurrent());
   if(BlockHour13 && hour == 13) return true;
   for(int i=0;i<r_BlockedHoursCount;i++) if(hour==r_BlockedHoursArr[i]) return true;
   if(r_BlockToxicCombos) {
      if(hour==14 && dow==2) return true;
      if(hour==11 && dow==1) return true;
      if(hour==14 && dow==4) return true;
      if(hour==16 && dow==1) return true;
   }
   return false;
}

bool IsVolatilityOK() {
   double atr = iATR(Symbol(), PERIOD_H1, ATR_Period, 0);
   double a = atr / g_pipValue;
   if(a < r_ATR_MinPips) return false;
   if(r_ATR_MaxPips > 0 && a > r_ATR_MaxPips) return false;
   return true;
}

bool IsEMA50DistanceOK() {
   if(!UseEMA50DistFilter) return true;
   double ema50 = iMA(Symbol(), PERIOD_H1, TrendEMA_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
   double price = (MarketInfo(Symbol(),MODE_BID)+MarketInfo(Symbol(),MODE_ASK))/2.0;
   if(MathAbs(price-ema50)/g_pipValue > r_MaxEMA50DistPips) return false;
   return true;
}

//+------------------------------------------------------------------+
int CountOpenTrades() {
   int count=0;
   for(int i=OrdersTotal()-1;i>=0;i--)
      if(OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
         if(OrderSymbol()==Symbol() && OrderMagicNumber()==MagicNumber) count++;
   return count;
}

int GetTrendDirection() {
   double ema_now  = iMA(Symbol(),PERIOD_H1,TrendEMA_Period,0,MODE_EMA,PRICE_CLOSE,0);
   double ema_prev = iMA(Symbol(),PERIOD_H1,TrendEMA_Period,0,MODE_EMA,PRICE_CLOSE,r_TrendBars);
   double close_tf = iClose(Symbol(),PERIOD_H1,0);
   if(close_tf>ema_now && ema_now>ema_prev) return 1;
   if(close_tf<ema_now && ema_now<ema_prev) return -1;
   return 0;
}

//+------------------------------------------------------------------+
void CheckEntry() {
   int trend = GetTrendDirection();
   if(trend==0) return;

   double ema20 = iMA(Symbol(),PERIOD_M15,EntryEMA_Period,0,MODE_EMA,PRICE_CLOSE,0);
   double open1=iOpen(Symbol(),PERIOD_M15,1), close1=iClose(Symbol(),PERIOD_M15,1);
   double high1=iHigh(Symbol(),PERIOD_M15,1), low1=iLow(Symbol(),PERIOD_M15,1);
   double open2=iOpen(Symbol(),PERIOD_M15,2), close2=iClose(Symbol(),PERIOD_M15,2);
   double low2=iLow(Symbol(),PERIOD_M15,2), high2=iHigh(Symbol(),PERIOD_M15,2);
   double body1=MathAbs(close1-open1), range1=high1-low1, body2=MathAbs(close2-open2);
   double bid=MarketInfo(Symbol(),MODE_BID), ask=MarketInfo(Symbol(),MODE_ASK);
   double rsi=iRSI(Symbol(),PERIOD_M15,RSI_Period,PRICE_CLOSE,1);

   if(trend==1) {
      if(rsi>RSI_OB) return;
      double ema20_b2=iMA(Symbol(),PERIOD_M15,EntryEMA_Period,0,MODE_EMA,PRICE_CLOSE,2);
      if(low2>ema20_b2) return;
      if(close1<=ema20) return;
      if(close1<=open1) return;
      if(range1>0 && body1/range1<0.6) return;
      if(body1<=body2) return;
      double sl=low1;
      for(int i=1;i<=r_SL_SwingBars;i++){ double l=iLow(Symbol(),PERIOD_M15,i); if(l<sl) sl=l; }
      sl-=2*g_pipValue;
      double slDist=(ask-sl)/g_pipValue;
      if(slDist<r_MinSL_Pips||slDist>r_MaxSL_Pips) return;
      double tp=ask+(ask-sl)*r_MinRR;
      ExecuteTrade(OP_BUY,ask,sl,tp,"EMA Pullback Buy");
   }
   if(trend==-1) {
      if(rsi<RSI_OS) return;
      double ema20_b2=iMA(Symbol(),PERIOD_M15,EntryEMA_Period,0,MODE_EMA,PRICE_CLOSE,2);
      if(high2<ema20_b2) return;
      if(close1>=ema20) return;
      if(close1>=open1) return;
      if(range1>0 && body1/range1<0.6) return;
      if(body1<=body2) return;
      double sl=high1;
      for(int i=1;i<=r_SL_SwingBars;i++){ double h=iHigh(Symbol(),PERIOD_M15,i); if(h>sl) sl=h; }
      sl+=2*g_pipValue;
      double slDist=(sl-bid)/g_pipValue;
      if(slDist<r_MinSL_Pips||slDist>r_MaxSL_Pips) return;
      double tp=bid-(sl-bid)*r_MinRR;
      ExecuteTrade(OP_SELL,bid,sl,tp,"EMA Pullback Sell");
   }
}

//+------------------------------------------------------------------+
void CheckPyramidClose() {
   if(!UsePyramid) return;
   if(!g_pyr.waitingForClose) return;
   if(g_pyr.lastTicket<=0){ g_pyr.waitingForClose=false; return; }

   bool stillOpen=false;
   for(int i=0;i<OrdersTotal();i++)
      if(OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
         if(OrderTicket()==g_pyr.lastTicket && OrderSymbol()==Symbol()) stillOpen=true;
   if(stillOpen) return;

   for(int i=OrdersHistoryTotal()-1;i>=0;i--) {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)) continue;
      if(OrderTicket()!=g_pyr.lastTicket || OrderSymbol()!=Symbol()) continue;
      double pnl=OrderProfit()+OrderSwap()+OrderCommission();
      bool wasReverse=g_pyr.lastTradeIsReverse;
      int  wasLevel=g_pyr.lastTradeLevel;
      int  wasType=g_pyr.lastTradeType;
      g_pyr.waitingForClose=false; g_pyr.lastTicket=0;

      if(wasReverse) { SaveState(); return; }

      if(wasLevel==0) AddL0Result(pnl>0);
      if(pnl>0) {
         g_pyr.streak++; g_pyr.consecLosses=0;
         if(g_pyr.streak>MaxStreakLevel) g_pyr.streak=MaxStreakLevel;
      } else {
         int oldStreak=g_pyr.streak;
         g_pyr.streak=0; g_pyr.consecLosses++;
         bool cold=IsSignalCold();
         if(UseReverseTrade) {
            bool should=false;
            if(wasLevel==0 && UseReverseOnL0)
               should=(RevMinConsecLosses<=0 || g_pyr.consecLosses>=RevMinConsecLosses);
            else if(wasLevel==2 && UseReverseOnL2)
               should=cold;
            if(should) ExecuteReverseTrade(wasType,wasLevel);
         }
      }
      SaveState();
      return;
   }
   // ticket not found (e.g. history not loaded) -> reset waiting to avoid stall
   g_pyr.waitingForClose=false;
   SaveState();
}

//+------------------------------------------------------------------+
void AddL0Result(bool isWin) {
   int window=MathMin(RollingWR_Window,20);
   g_rollingL0[g_rollingL0_index]=isWin?1:0;
   g_rollingL0_index=(g_rollingL0_index+1)%window;
   if(g_rollingL0_count<window) g_rollingL0_count++;
}

double GetRollingWR() {
   if(g_rollingL0_count==0) return 50.0;
   int wins=0;
   for(int i=0;i<g_rollingL0_count;i++) wins+=g_rollingL0[i];
   return (double)wins/(double)g_rollingL0_count*100.0;
}

bool IsSignalCold() { return (GetRollingWR()<=RollingWR_Threshold); }

//+------------------------------------------------------------------+
void ExecuteReverseTrade(int originalType,int originalLevel=0) {
   int revHour=TimeHour(TimeCurrent());
   if(revHour>=13 && revHour<=14) return;
   if(revHour>=17) return;
   if(g_dailyTrades>=r_MaxTradesPerDay) return;
   if(CountOpenTrades()>=1) return;

   double bid=MarketInfo(Symbol(),MODE_BID), ask=MarketInfo(Symbol(),MODE_ASK);
   if(originalType==OP_BUY) {
      double sl=iHigh(Symbol(),PERIOD_M15,1);
      for(int i=1;i<=r_SL_SwingBars;i++){ double h=iHigh(Symbol(),PERIOD_M15,i); if(h>sl) sl=h; }
      sl+=2*g_pipValue;
      double slDist=(sl-bid)/g_pipValue;
      if(slDist<=0) return;
      if(RevMaxSL_Pips>0 && slDist>RevMaxSL_Pips) return;
      double tp=bid-(sl-bid)*r_MinRR;
      ExecuteTradeReverse(OP_SELL,bid,sl,tp,"EMA Reverse Sell",originalLevel);
   } else if(originalType==OP_SELL) {
      double sl=iLow(Symbol(),PERIOD_M15,1);
      for(int i=1;i<=r_SL_SwingBars;i++){ double l=iLow(Symbol(),PERIOD_M15,i); if(l<sl) sl=l; }
      sl-=2*g_pipValue;
      double slDist=(ask-sl)/g_pipValue;
      if(slDist<=0) return;
      if(RevMaxSL_Pips>0 && slDist>RevMaxSL_Pips) return;
      double tp=ask+(ask-sl)*r_MinRR;
      ExecuteTradeReverse(OP_BUY,ask,sl,tp,"EMA Reverse Buy",originalLevel);
   }
}

//+------------------------------------------------------------------+
void ExecuteTradeReverse(int type,double price,double sl,double tp,string comment,int fromLevel=0) {
   double slDist=MathAbs(price-sl);
   if(slDist<=0) return;
   double riskMult;
   if(UseRevLotFromLevel) riskMult=(fromLevel==2)?r_L2_LotMult:r_L0_LotMult;
   else                   riskMult=RevLotMult;
   if(r_ReduceThursdayRisk && TimeDayOfWeek(TimeCurrent())==4){
      riskMult*=r_ThursdayRiskMult; comment=comment+"|THU_REDUCED";
   }
   comment=comment+"|REV|L"+IntegerToString(fromLevel);
   double lotSize=CalculateLotSize(slDist,riskMult);
   if(lotSize<=0) return;
   price=NormalizeDouble(price,g_digits); sl=NormalizeDouble(sl,g_digits); tp=NormalizeDouble(tp,g_digits);
   string fullComment=comment+"|R="+DoubleToStr(slDist,g_digits);
   int ticket=OrderSend(Symbol(),type,lotSize,price,3,sl,tp,fullComment,MagicNumber,0,
                        type==OP_BUY?clrBlue:clrOrange);
   if(ticket<0){ Print("REVERSE OrderSend failed: ",GetLastError()); }
   else {
      g_dailyTrades++;
      g_pyr.lastTicket=ticket; g_pyr.waitingForClose=true;
      g_pyr.lastTradeIsReverse=true; g_pyr.lastTradeLevel=0; g_pyr.lastTradeType=type;
      SaveState();
      Print("REVERSE opened #",ticket," ",comment," lots ",lotSize);
   }
}

//+------------------------------------------------------------------+
void ExecuteTrade(int type,double price,double sl,double tp,string comment) {
   double slDist=MathAbs(price-sl);
   double riskMult=1.0;
   if(r_ReduceThursdayRisk && TimeDayOfWeek(TimeCurrent())==4){
      riskMult=r_ThursdayRiskMult; comment=comment+"|THU_REDUCED";
   }
   double pyrMult=1.0;
   if(UsePyramid){
      if(g_pyr.streak==0) pyrMult=r_L0_LotMult;
      else if(g_pyr.streak==1) pyrMult=r_L1_LotMult;
      else pyrMult=r_L2_LotMult;
      riskMult*=pyrMult; comment=comment+"|L"+IntegerToString(g_pyr.streak);
   }
   double lotSize=CalculateLotSize(slDist,riskMult);
   if(lotSize<=0) return;
   price=NormalizeDouble(price,g_digits); sl=NormalizeDouble(sl,g_digits); tp=NormalizeDouble(tp,g_digits);
   string fullComment=comment+"|R="+DoubleToStr(slDist,g_digits);
   int ticket=OrderSend(Symbol(),type,lotSize,price,3,sl,tp,fullComment,MagicNumber,0,
                        type==OP_BUY?clrGreen:clrRed);
   if(ticket<0){ Print("OrderSend failed: ",GetLastError()); }
   else {
      g_dailyTrades++;
      g_pyr.lastTicket=ticket; g_pyr.waitingForClose=true;
      g_pyr.lastTradeLevel=g_pyr.streak; g_pyr.lastTradeIsReverse=false; g_pyr.lastTradeType=type;
      SaveState();
      Print("Trade opened #",ticket," ",comment," L",g_pyr.streak," lots ",lotSize);
   }
}

//+------------------------------------------------------------------+
double CalculateLotSize(double slDistance,double riskMultiplier=1.0) {
   if(slDistance<=0) return 0;
   double riskMoney=AccountBalance()*RiskPercent/100.0*riskMultiplier;
   double tickValue=MarketInfo(Symbol(),MODE_TICKVALUE);
   double tickSize=MarketInfo(Symbol(),MODE_TICKSIZE);
   if(tickValue==0||tickSize==0) return 0;
   double slTicks=slDistance/tickSize;
   double lotSize=riskMoney/(slTicks*tickValue);
   double minLot=MarketInfo(Symbol(),MODE_MINLOT), maxLot=MarketInfo(Symbol(),MODE_MAXLOT);
   double lotStep=MarketInfo(Symbol(),MODE_LOTSTEP);
   lotSize=MathFloor(lotSize/lotStep)*lotStep;
   lotSize=MathMax(minLot,MathMin(maxLot,lotSize));
   return NormalizeDouble(lotSize,2);
}

//+------------------------------------------------------------------+
void ManageOpenTrades() {
   for(int i=OrdersTotal()-1;i>=0;i--) {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderSymbol()!=Symbol()||OrderMagicNumber()!=MagicNumber) continue;
      double openPrice=OrderOpenPrice(), currentSL=OrderStopLoss();
      int ticket=OrderTicket();
      double riskDist=GetInitialRisk(OrderComment(),MathAbs(openPrice-currentSL));
      if(riskDist<=0) continue;
      if(OrderType()==OP_BUY) {
         double cur=MarketInfo(Symbol(),MODE_BID), profit=cur-openPrice;
         if(UseBreakeven && profit>=riskDist*r_BE_Trigger_R && currentSL<openPrice){
            double beSL=openPrice+1*g_pipValue;
            if(!OrderModify(ticket,openPrice,NormalizeDouble(beSL,g_digits),OrderTakeProfit(),0,clrYellow))
               Print("BE modify failed: ",GetLastError());
         }
      } else if(OrderType()==OP_SELL) {
         double cur=MarketInfo(Symbol(),MODE_ASK), profit=openPrice-cur;
         if(UseBreakeven && profit>=riskDist*r_BE_Trigger_R && currentSL>openPrice){
            double beSL=openPrice-1*g_pipValue;
            if(!OrderModify(ticket,openPrice,NormalizeDouble(beSL,g_digits),OrderTakeProfit(),0,clrYellow))
               Print("BE modify failed: ",GetLastError());
         }
      }
   }
}

//+------------------------------------------------------------------+
double GetInitialRisk(string comment,double fallback) {
   int pos=StringFind(comment,"|R=");
   if(pos<0) return fallback;
   double r=StringToDouble(StringSubstr(comment,pos+3));
   return (r>0)?r:fallback;
}
//+------------------------------------------------------------------+
