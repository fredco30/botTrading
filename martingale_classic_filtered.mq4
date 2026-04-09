//+------------------------------------------------------------------+
//|                             martingale_classic_filtered.mq4      |
//|                                                                  |
//|  STRATEGIE: Martingale Classique SAME DIRECTION avec filtres    |
//|                                                                  |
//|  Logique:                                                        |
//|    1. Signal INIT (EMA200 + MACD + RSI) -> ouverture 1x lot     |
//|    2. Si SL -> attendre prochain signal MEME direction -> 2x    |
//|    3. Si 2x SL -> attendre prochain signal MEME direction -> 4x |
//|    4. Cap a 3 niveaux (1x -> 2x -> 4x -> reset)                 |
//|    5. TOUT win -> reset complet                                  |
//|    6. Filtre H x J: 27 cellules toxiques bannies                |
//|    7. Max 1 cycle complet par jour                               |
//|    8. Timeout cycle: 24h                                         |
//+------------------------------------------------------------------+
#property copyright "Martingale Classic Filtered"
#property version   "1.00"
#property strict
#property description "Classic martingale same-direction with H*J filter"

// ============================================================================
// INPUTS
// ============================================================================

input group "=== SIGNAL ==="
input int    Inp_EMA_Period      = 200;
input int    Inp_MACD_Fast       = 12;
input int    Inp_MACD_Slow       = 26;
input int    Inp_RSI_Period      = 14;

input group "=== TRADE ==="
input int    Inp_ATR_Period      = 14;
input double Inp_SL_Mult         = 1.5;
input double Inp_TP_Mult         = 2.0;
input double Inp_RiskPct         = 1.0;      // % risk base lot

input group "=== MARTINGALE ==="
input bool   Inp_UseMartingale   = true;
input double Inp_MgMult          = 2.0;      // lot multiplier next level
input int    Inp_MaxLevel        = 2;        // 0=INIT, 1=Mg1, 2=Mg2 -> cap 3 niveaux
input int    Inp_CycleTimeoutHr  = 24;       // reset cycle after N hours

input group "=== FILTRES H x J ==="
input bool   Inp_UseFilter       = true;     // activer filtre cellules toxiques

input group "=== PROTECTION ==="
input double Inp_MaxDD           = 30.0;
input bool   Inp_OneCyclePerDay  = true;     // max 1 cycle complet par jour

input group "=== TIME ==="
input bool   Inp_UseTime         = true;
input int    Inp_StartHr         = 8;
input int    Inp_EndHr           = 21;

input group "=== SYSTEM ==="
input int    Inp_Magic           = 112300;
input int    Inp_Slip            = 3;
input string Inp_Prefix          = "MCF";
input bool   Inp_Log             = true;

// ============================================================================
// STRUCTURES & GLOBALS
// ============================================================================

struct State {
    int    level;            // 0 = INIT, 1 = Mg1, 2 = Mg2
    int    lastLosingDir;    // OP_BUY or OP_SELL - direction we wait for
    double baseLot;          // lot of the INIT
    int    lastTicket;
    bool   waitingForClose;  // true if a trade is in flight
    bool   cycleActive;      // true if we are waiting for next mg signal
    datetime cycleStart;     // time when the cycle started (for timeout)
};

double g_pt;
int    g_dig;
datetime g_lastBar = 0;
State  g_st;

// Counters
int g_cycles = 0;
int g_cyclesWon = 0;
int g_cyclesLost = 0;
int g_trades = 0;

// Day reset
datetime g_lastDay = 0;
bool     g_cycleDoneToday = false;

// H x J toxic cells: index = dow*24 + hour
bool g_toxic[168];

// ============================================================================
// UTILITIES
// ============================================================================

double Norm(double p) { return NormalizeDouble(p, g_dig); }
double MinD(double a,double b) { return(a<b)?a:b; }
double MaxD(double a,double b) { return(a>b)?a:b; }

bool IsNewBar() {
    datetime cb=iTime(NULL,0,0);
    if(cb==g_lastBar) return false;
    g_lastBar=cb; return true;
}

void LogMsg(string m,bool imp=false) {
    if(!Inp_Log && !imp) return;
    Print(StringFormat("%s %s %s",imp?"[!]":"[*]",TimeToString(TimeCurrent()),m));
}

// ============================================================================
// TOXIC CELLS INIT
// ============================================================================

void InitToxicCells() {
    for(int i=0; i<168; i++) g_toxic[i]=false;

    // Lundi (dow=1)
    g_toxic[1*24+10]=true;
    g_toxic[1*24+16]=true;
    g_toxic[1*24+18]=true;

    // Mardi (dow=2)
    g_toxic[2*24+8]=true;
    g_toxic[2*24+10]=true;
    g_toxic[2*24+12]=true;
    g_toxic[2*24+13]=true;
    g_toxic[2*24+14]=true;
    g_toxic[2*24+19]=true;
    g_toxic[2*24+20]=true;
    g_toxic[2*24+21]=true;

    // Mercredi (dow=3)
    g_toxic[3*24+8]=true;
    g_toxic[3*24+14]=true;
    g_toxic[3*24+19]=true;
    g_toxic[3*24+21]=true;

    // Jeudi (dow=4)
    g_toxic[4*24+11]=true;
    g_toxic[4*24+12]=true;
    g_toxic[4*24+15]=true;
    g_toxic[4*24+18]=true;
    g_toxic[4*24+20]=true;

    // Vendredi (dow=5) - whole afternoon toxic
    g_toxic[5*24+11]=true;
    g_toxic[5*24+12]=true;
    g_toxic[5*24+13]=true;
    g_toxic[5*24+14]=true;
    g_toxic[5*24+16]=true;
    g_toxic[5*24+17]=true;
    g_toxic[5*24+18]=true;
}

bool IsToxicNow() {
    if(!Inp_UseFilter) return false;
    int dow=DayOfWeek();
    int h=TimeHour(TimeCurrent());
    int idx=dow*24+h;
    if(idx<0||idx>=168) return false;
    return g_toxic[idx];
}

// ============================================================================
// INIT / DEINIT
// ============================================================================

int OnInit() {
    g_dig=(int)MarketInfo(Symbol(),MODE_DIGITS);
    g_pt=(g_dig==3||g_dig==5)?MarketInfo(Symbol(),MODE_POINT)*10:MarketInfo(Symbol(),MODE_POINT);

    InitToxicCells();
    ResetCycle();

    LogMsg(StringFormat("=== MCF READY | Mg:%s Mult:%.1f MaxLvl:%d Filter:%s ===",
        Inp_UseMartingale?"ON":"OFF", Inp_MgMult, Inp_MaxLevel, Inp_UseFilter?"ON":"OFF"),true);

    return INIT_SUCCEEDED;
}

void OnDeinit(const int& reason) {
    LogMsg(StringFormat("=== MCF STOP | Cycles:%d Won:%d Lost:%d Trades:%d ===",
        g_cycles, g_cyclesWon, g_cyclesLost, g_trades),true);
}

// ============================================================================
// RESET CYCLE
// ============================================================================

void ResetCycle() {
    g_st.level=0;
    g_st.lastLosingDir=-1;
    g_st.baseLot=0;
    g_st.lastTicket=0;
    g_st.waitingForClose=false;
    g_st.cycleActive=false;
    g_st.cycleStart=0;
}

// ============================================================================
// MAIN TICK
// ============================================================================

void OnTick() {
    // Day reset
    string today=TimeToStr(TimeCurrent(),TIME_DATE);
    if(today!=g_lastDay) {
        g_lastDay=today;
        g_cycleDoneToday=false;
    }

    if(!PreChecks()) return;

    // Tick-level: check if current trade closed -> evolve state
    CheckTradeClosed();

    // Bar-level: open new trades only on new bar close
    if(!IsNewBar()) return;

    // Cycle timeout check
    if(g_st.cycleActive && g_st.cycleStart>0) {
        int elapsedHr=(int)((TimeCurrent()-g_st.cycleStart)/3600);
        if(elapsedHr>=Inp_CycleTimeoutHr) {
            LogMsg("Cycle TIMEOUT -> reset",true);
            g_cyclesLost++;
            ResetCycle();
        }
    }

    // No trade in flight -> try to open
    if(CountMyTrades()==0 && !g_st.waitingForClose) {
        // Max 1 cycle per day
        if(Inp_OneCyclePerDay && g_cycleDoneToday && !g_st.cycleActive) return;

        int sig=GetSignal();
        if(sig==0) return;

        if(g_st.cycleActive) {
            // In cycle: open next Mg only if signal matches losing direction
            int desiredDir=(g_st.lastLosingDir==OP_BUY)?1:-1;
            if(sig==desiredDir) {
                OpenMgLevel();
            }
        } else {
            // Fresh INIT - filter applies only on NEW cycle start
            if(IsToxicNow()) return;
            if(sig==1) OpenInitial(OP_BUY);
            else if(sig==-1) OpenInitial(OP_SELL);
        }
    }
}

// ============================================================================
// CHECK TRADE CLOSED (tick level)
// ============================================================================

void CheckTradeClosed() {
    if(!g_st.waitingForClose) return;
    if(g_st.lastTicket<=0) { ResetCycle(); return; }

    // Check if still open
    bool stillOpen=false;
    for(int i=0;i<OrdersTotal();i++) {
        if(OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
            if(OrderTicket()==g_st.lastTicket && OrderSymbol()==Symbol())
                stillOpen=true;
    }
    if(stillOpen) return;

    // Closed - find in history
    for(int i=OrdersHistoryTotal()-1; i>=0; i--) {
        if(!OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)) continue;
        if(OrderTicket()!=g_st.lastTicket || OrderSymbol()!=Symbol()) continue;

        double pnl=OrderProfit()+OrderSwap()+OrderCommission();
        int    type=OrderType();

        g_st.waitingForClose=false;

        if(pnl>0) {
            // WIN - reset full cycle
            if(g_st.cycleActive || g_st.level>0) {
                g_cyclesWon++;
                g_cycleDoneToday=true;
                LogMsg(StringFormat("CYCLE WIN lvl=%d pnl=%.2f",g_st.level,pnl),true);
            } else {
                // Simple INIT win (no cycle started)
                g_cyclesWon++;
                g_cycleDoneToday=true;
                LogMsg(StringFormat("INIT WIN pnl=%.2f",pnl));
            }
            ResetCycle();
        } else {
            // LOSS
            g_st.lastLosingDir=type;  // remember direction
            g_st.level++;

            if(g_st.level>Inp_MaxLevel) {
                // Cap reached - cycle lost, reset
                g_cyclesLost++;
                g_cycleDoneToday=true;
                LogMsg(StringFormat("CYCLE LOST lvl=%d pnl=%.2f",g_st.level-1,pnl),true);
                ResetCycle();
            } else {
                // Enter martingale waiting mode
                if(!g_st.cycleActive) {
                    g_st.cycleActive=true;
                    g_st.cycleStart=TimeCurrent();
                    g_cycles++;
                }
                LogMsg(StringFormat("LOSS lvl=%d pnl=%.2f -> wait Mg%d (%s)",
                    g_st.level-1, pnl, g_st.level,
                    (g_st.lastLosingDir==OP_BUY)?"BUY":"SELL"));
            }
        }
        return;
    }
}

// ============================================================================
// OPEN INITIAL (level 0)
// ============================================================================

void OpenInitial(int type) {
    double atr=iATR(NULL,0,Inp_ATR_Period,1);
    if(atr<=0) return;

    double pr=(type==OP_BUY)?Ask:Bid;
    double sl,tp;
    if(type==OP_BUY) {
        sl=Norm(Ask-Inp_SL_Mult*atr);
        tp=Norm(Ask+Inp_TP_Mult*atr);
    } else {
        sl=Norm(Bid+Inp_SL_Mult*atr);
        tp=Norm(Bid-Inp_TP_Mult*atr);
    }

    double lots=CalcBaseLots();
    if(lots<=0) return;

    g_st.baseLot=lots;

    string dir=(type==OP_BUY)?"B":"S";
    string cmnt=StringFormat("%s-L0-%s",Inp_Prefix,dir);
    color clr=(type==OP_BUY)?clrGreen:clrRed;

    int tk=OrderSend(Symbol(),type,lots,pr,Inp_Slip,sl,tp,cmnt,Inp_Magic,0,clr);
    if(tk>0) {
        g_st.lastTicket=tk;
        g_st.waitingForClose=true;
        g_st.level=0;
        g_trades++;
        LogMsg(StringFormat("INIT L0 %s Tk:%d Lot:%.2f @%.5f SL:%.5f TP:%.5f",
            dir,tk,lots,pr,sl,tp),true);
    }
}

// ============================================================================
// OPEN MARTINGALE LEVEL (1, 2, ...)
// ============================================================================

void OpenMgLevel() {
    if(!Inp_UseMartingale) { ResetCycle(); return; }

    int type=g_st.lastLosingDir;  // SAME direction
    if(type!=OP_BUY && type!=OP_SELL) { ResetCycle(); return; }

    double atr=iATR(NULL,0,Inp_ATR_Period,1);
    if(atr<=0) return;

    double pr=(type==OP_BUY)?Ask:Bid;
    double sl,tp;
    if(type==OP_BUY) {
        sl=Norm(Ask-Inp_SL_Mult*atr);
        tp=Norm(Ask+Inp_TP_Mult*atr);
    } else {
        sl=Norm(Bid+Inp_SL_Mult*atr);
        tp=Norm(Bid-Inp_TP_Mult*atr);
    }

    // Lot = baseLot * MgMult^level
    double lots=g_st.baseLot;
    for(int i=0;i<g_st.level;i++) lots*=Inp_MgMult;

    double maxL=MarketInfo(Symbol(),MODE_MAXLOT);
    double stp=MarketInfo(Symbol(),MODE_LOTSTEP);
    lots=MinD(lots,maxL);
    lots=MathFloor(lots/stp)*stp;
    lots=NormalizeDouble(lots,2);
    if(lots<=0) { ResetCycle(); return; }

    string dir=(type==OP_BUY)?"B":"S";
    string cmnt=StringFormat("%s-L%d-%s",Inp_Prefix,g_st.level,dir);
    color clr=(type==OP_BUY)?clrBlue:clrOrange;

    int tk=OrderSend(Symbol(),type,lots,pr,Inp_Slip,sl,tp,cmnt,Inp_Magic,0,clr);
    if(tk>0) {
        g_st.lastTicket=tk;
        g_st.waitingForClose=true;
        g_trades++;
        LogMsg(StringFormat("Mg%d %s Tk:%d Lot:%.2f @%.5f SL:%.5f TP:%.5f",
            g_st.level,dir,tk,lots,pr,sl,tp),true);
    } else {
        LogMsg(StringFormat("Mg ERR:%d",GetLastError()),true);
    }
}

// ============================================================================
// SIGNAL (same as baseline)
// ============================================================================

int GetSignal() {
    int sc=0;

    double ema=iMA(NULL,0,Inp_EMA_Period,0,MODE_EMA,PRICE_CLOSE,1);
    if(Close[1]>ema) sc++; else if(Close[1]<ema) sc--;

    double macd=iMACD(NULL,0,Inp_MACD_Fast,Inp_MACD_Slow,9,PRICE_CLOSE,MODE_MAIN,1);
    double macdSig=iMACD(NULL,0,Inp_MACD_Fast,Inp_MACD_Slow,9,PRICE_CLOSE,MODE_SIGNAL,1);
    if(macd>macdSig && macd>0) sc++; else if(macd<macdSig && macd<0) sc--;

    double rsi=iRSI(NULL,0,Inp_RSI_Period,PRICE_CLOSE,1);
    if(rsi>50&&rsi<72) sc++; else if(rsi<50&&rsi>28) sc--;

    if(sc>=2) return 1;
    if(sc<=-2) return -1;
    return 0;
}

// ============================================================================
// POSITION MGMT
// ============================================================================

int CountMyTrades() {
    int c=0;
    for(int i=0;i<OrdersTotal();i++) {
        if(OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
            if(OrderSymbol()==Symbol() && OrderMagicNumber()==Inp_Magic &&
               (OrderType()==OP_BUY||OrderType()==OP_SELL)) c++;
    }
    return c;
}

// ============================================================================
// LOT CALCULATION (base lot only - Mg multiplies afterwards)
// ============================================================================

double CalcBaseLots() {
    double bal=AccountBalance();
    double riskAmt=bal*Inp_RiskPct/100.0;

    double atr=iATR(NULL,0,Inp_ATR_Period,1);
    double slDist=Inp_SL_Mult*atr;
    if(slDist<=0) slDist=atr;

    double tVal=MarketInfo(Symbol(),MODE_TICKVALUE);
    double tSiz=MarketInfo(Symbol(),MODE_TICKSIZE);
    if(tVal<=0||tSiz<=0) return MarketInfo(Symbol(),MODE_MINLOT);

    double lots=riskAmt/((slDist/tSiz)*tVal);

    double minL=MarketInfo(Symbol(),MODE_MINLOT);
    double maxL=MarketInfo(Symbol(),MODE_MAXLOT);
    double stp=MarketInfo(Symbol(),MODE_LOTSTEP);

    lots=MaxD(minL,MinD(lots,maxL));
    lots=MathFloor(lots/stp)*stp;

    return NormalizeDouble(lots,2);
}

// ============================================================================
// PRE-CHECKS
// ============================================================================

bool PreChecks() {
    if(!IsConnected()||!IsTradeAllowed()) return false;
    if((int)MarketInfo(Symbol(),MODE_SPREAD)>30) return false;

    if(Inp_UseTime) {
        int h=TimeHour(TimeCurrent());
        if(h<Inp_StartHr||h>Inp_EndHr) return false;
    }

    int dow=DayOfWeek();
    if(dow==0||dow==6) return false;
    if(dow==5&&TimeHour(TimeCurrent())>20) return false;

    double eq=AccountEquity();
    double bal=AccountBalance();
    if(bal>0 && ((bal-eq)/bal*100)>Inp_MaxDD) return false;

    return true;
}
//+------------------------------------------------------------------+
