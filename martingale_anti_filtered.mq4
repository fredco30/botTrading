//+------------------------------------------------------------------+
//|                              martingale_anti_filtered.mq4        |
//|                                                                  |
//|  STRATEGIE: Anti-Martingale (pyramid on wins) avec filtres      |
//|                                                                  |
//|  Logique:                                                        |
//|    1. Signal INIT (EMA200 + MACD + RSI) + filtre H x J          |
//|    2. Lot = base_lot * MgMult ^ streak                          |
//|       - Streak 0 (base):       1.00x                            |
//|       - Streak 1 (apres 1 win): 1.50x                           |
//|       - Streak 2 (apres 2 wins): 2.25x                          |
//|    3. WIN -> streak++ (cap a MaxLevel)                          |
//|    4. LOSS -> streak = 0 (reset immediat)                       |
//|    5. Filtre H x J (27 cellules calibrees 2023-2026)           |
//|    6. Filtre ATR: skip si volatilite anormale (news chaos)       |
//|    7. Pas de cycle-lock : chaque trade est independant           |
//|    8. Streak persiste a travers les jours (pas de reset daily)  |
//|                                                                  |
//|  v2: filtre ATR ajoute pour eviter les regimes chaotiques       |
//|  v3: seuil ATR fixe en pips (15p) au lieu du rolling ratio      |
//|  v5: multiplicateurs par niveau L0/L1/L2 (v4 = 7cells abandonne)|
//|      L0 reduit a 0.3 (perdant structurellement, evite le drain) |
//|      L1/L2 tunables pour optimisation fine                      |
//+------------------------------------------------------------------+
#property copyright "Anti-Martingale Filtered v5"
#property version   "5.00"
#property strict
#property description "Anti-mart + H*J(27) + ATR(15p) + per-level lot multipliers"

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

input group "=== ANTI-MARTINGALE ==="
input bool   Inp_UsePyramid      = true;     // activer la pyramide sur wins
input double Inp_L0_LotMult      = 0.3;      // multiplicateur lot L0 (signal de base, perdant seul)
input double Inp_L1_LotMult      = 1.5;      // multiplicateur lot L1 (apres 1 win - PROFIT ENGINE)
input double Inp_L2_LotMult      = 2.25;     // multiplicateur lot L2 (apres 2 wins)
input int    Inp_MaxLevel        = 2;        // cap du streak (2 -> 3 niveaux: L0, L1, L2)
input bool   Inp_ResetOnNewDay   = false;    // reset streak chaque nouveau jour
// Note: Inp_MgMult est deprecie (remplace par les 3 inputs L0/L1/L2 ci-dessus)
input double Inp_MgMult          = 1.5;      // (deprecie, garde pour compat backward)

input group "=== FILTRES H x J ==="
input bool   Inp_UseFilter       = true;     // activer filtre cellules toxiques

input group "=== FILTRE ATR (volatilite anormale) ==="
input bool   Inp_UseATRFilter    = true;     // skip si ATR > seuil (news chaos)
input double Inp_ATRMaxPips      = 15.0;     // seuil ATR en pips (0 = pas de filtre)
// Note: 15 pips calibre pour EURUSD H1 (analyse historique 2023-2026).
// Pour autres paires, ajuster en consequence.

input group "=== PROTECTION ==="
input double Inp_MaxDD           = 30.0;
input int    Inp_MaxDayTrades    = 20;

input group "=== TIME ==="
input bool   Inp_UseTime         = true;
input int    Inp_StartHr         = 8;
input int    Inp_EndHr           = 21;

input group "=== SYSTEM ==="
input int    Inp_Magic           = 112405;
input int    Inp_Slip            = 3;
input string Inp_Prefix          = "AMF5";
input bool   Inp_Log             = true;

// ============================================================================
// STRUCTURES & GLOBALS
// ============================================================================

struct State {
    int    streak;           // 0 = base, 1 = after 1 win, 2 = after 2 wins, ...
    int    lastTicket;
    bool   waitingForClose;
};

double g_pt;
int    g_dig;
datetime g_lastBar = 0;
State  g_st;

// Counters
int g_trades = 0;
int g_wins = 0;
int g_losses = 0;
int g_maxStreakReached = 0;

// Day tracking
datetime g_lastDay = 0;
int      g_dayTrades = 0;

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
// TOXIC CELLS INIT - 27 cells calibrated on 2023-2026
// ============================================================================
// NOTE: calibre sur 2023-2026 uniquement. Optimal pour ce regime (post-COVID,
// trend USD). Peut ne pas generaliser sur d'autres periodes (2020-2022 par ex).
// Le filtre "7 cellules robustes" walk-forward a ete teste et s'est avere
// DESASTREUX en live malgre une simulation Python positive - la pyramide casse
// quand on laisse passer trop de trades, ce que la simulation ne modelisait pas.

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
// ATR FILTER: skip si volatilite anormale (chaos news-driven)
// ============================================================================
// Seuil FIXE en pips. Plus simple et plus robuste qu'un rolling (qui s'adapte
// aux regimes chaotiques soutenus et perd son efficacite).
// Sur EURUSD H1, l'analyse historique montre que les trades avec ATR > 15 pips
// ont un WR et un PnL significativement plus mauvais.
bool IsATRTooHigh() {
    if(!Inp_UseATRFilter) return false;
    if(Inp_ATRMaxPips<=0) return false;
    double atr=iATR(NULL,0,Inp_ATR_Period,1);
    if(atr<=0) return false;
    // Conversion prix -> pips via g_pt (pip size, gere 4-digit et 5-digit brokers)
    double atrPips=atr/g_pt;
    return (atrPips > Inp_ATRMaxPips);
}

// ============================================================================
// INIT / DEINIT
// ============================================================================

int OnInit() {
    g_dig=(int)MarketInfo(Symbol(),MODE_DIGITS);
    g_pt=(g_dig==3||g_dig==5)?MarketInfo(Symbol(),MODE_POINT)*10:MarketInfo(Symbol(),MODE_POINT);

    InitToxicCells();
    ResetState();

    LogMsg(StringFormat("=== AMF READY | Lots L0:%.2fx L1:%.2fx L2:%.2fx MaxLvl:%d | HxJ:%s ATR:%s ===",
        Inp_L0_LotMult, Inp_L1_LotMult, Inp_L2_LotMult, Inp_MaxLevel,
        Inp_UseFilter?"ON":"OFF", Inp_UseATRFilter?"ON":"OFF"),true);

    return INIT_SUCCEEDED;
}

void OnDeinit(const int& reason) {
    LogMsg(StringFormat("=== AMF STOP | Trades:%d Wins:%d Losses:%d MaxStreak:%d ===",
        g_trades, g_wins, g_losses, g_maxStreakReached),true);
}

// ============================================================================
// RESET STATE
// ============================================================================

void ResetState() {
    g_st.streak=0;
    g_st.lastTicket=0;
    g_st.waitingForClose=false;
}

// ============================================================================
// MAIN TICK
// ============================================================================

void OnTick() {
    // Day reset (counter only; streak optionally)
    string today=TimeToStr(TimeCurrent(),TIME_DATE);
    if(today!=g_lastDay) {
        g_lastDay=today;
        g_dayTrades=0;
        if(Inp_ResetOnNewDay && g_st.streak>0 && !g_st.waitingForClose) {
            LogMsg(StringFormat("DAY RESET: streak %d -> 0",g_st.streak));
            g_st.streak=0;
        }
    }

    if(!PreChecks()) return;

    // [TICK LEVEL] Check if current trade closed -> update streak
    CheckTradeClosed();

    // [BAR LEVEL] Signal detection
    if(!IsNewBar()) return;

    if(CountMyTrades()==0 && !g_st.waitingForClose) {
        if(g_dayTrades>=Inp_MaxDayTrades) return;
        if(IsToxicNow()) return;
        if(IsATRTooHigh()) return;  // skip periodes de volatilite anormale (news chaos)

        int sig=GetSignal();
        if(sig==1) OpenTrade(OP_BUY);
        else if(sig==-1) OpenTrade(OP_SELL);
    }
}

// ============================================================================
// CHECK TRADE CLOSED (tick level) -> WIN streak++, LOSS reset
// ============================================================================

void CheckTradeClosed() {
    if(!g_st.waitingForClose) return;
    if(g_st.lastTicket<=0) { ResetState(); return; }

    // Check if still open
    bool stillOpen=false;
    for(int i=0;i<OrdersTotal();i++) {
        if(OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
            if(OrderTicket()==g_st.lastTicket && OrderSymbol()==Symbol())
                stillOpen=true;
    }
    if(stillOpen) return;

    // Find in history
    for(int i=OrdersHistoryTotal()-1; i>=0; i--) {
        if(!OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)) continue;
        if(OrderTicket()!=g_st.lastTicket || OrderSymbol()!=Symbol()) continue;

        double pnl=OrderProfit()+OrderSwap()+OrderCommission();
        g_st.waitingForClose=false;

        if(pnl>0) {
            // WIN -> pyramid up
            int oldStreak=g_st.streak;
            g_wins++;
            if(Inp_UsePyramid) {
                g_st.streak++;
                if(g_st.streak>Inp_MaxLevel) g_st.streak=Inp_MaxLevel;  // cap
            }
            if(g_st.streak>g_maxStreakReached) g_maxStreakReached=g_st.streak;
            double nextMult;
            if(g_st.streak==0)      nextMult=Inp_L0_LotMult;
            else if(g_st.streak==1) nextMult=Inp_L1_LotMult;
            else                    nextMult=Inp_L2_LotMult;
            LogMsg(StringFormat("WIN pnl=%.2f | streak %d -> %d (next lot x%.3f)",
                pnl, oldStreak, g_st.streak, nextMult),true);
        } else {
            // LOSS -> reset
            int oldStreak=g_st.streak;
            g_losses++;
            g_st.streak=0;
            LogMsg(StringFormat("LOSS pnl=%.2f | streak reset (was %d)",pnl,oldStreak),true);
        }
        g_st.lastTicket=0;
        return;
    }
}

// ============================================================================
// OPEN TRADE (with current pyramid lot)
// ============================================================================

void OpenTrade(int type) {
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

    // Base lot from current balance + pyramid multiplier par niveau
    double baseLot=CalcBaseLots();
    if(baseLot<=0) return;

    // Lot multiplier: un input dedie par niveau de pyramide.
    // L0 perd seul (PF 0.88), L1 est le profit engine (PF 1.53),
    // L2 amplifie (PF 1.14). On peut tuner chaque niveau independamment.
    double mult;
    if(g_st.streak==0)      mult=Inp_L0_LotMult;  // L0: 0.3 par defaut (reduit)
    else if(g_st.streak==1) mult=Inp_L1_LotMult;  // L1: 1.5 par defaut
    else                    mult=Inp_L2_LotMult;  // L2+: 2.25 par defaut
    double lots=baseLot*mult;

    double maxL=MarketInfo(Symbol(),MODE_MAXLOT);
    double minL=MarketInfo(Symbol(),MODE_MINLOT);
    double stp=MarketInfo(Symbol(),MODE_LOTSTEP);
    lots=MinD(lots,maxL);
    lots=MaxD(lots,minL);
    lots=MathFloor(lots/stp)*stp;
    lots=NormalizeDouble(lots,2);
    if(lots<=0) return;

    string dir=(type==OP_BUY)?"B":"S";
    string cmnt=StringFormat("%s-L%d-%s",Inp_Prefix,g_st.streak,dir);
    color clr;
    if(g_st.streak==0)      clr=(type==OP_BUY)?clrGreen:clrRed;
    else if(g_st.streak==1) clr=(type==OP_BUY)?clrLimeGreen:clrOrangeRed;
    else                    clr=(type==OP_BUY)?clrDarkGreen:clrFireBrick;

    int tk=OrderSend(Symbol(),type,lots,pr,Inp_Slip,sl,tp,cmnt,Inp_Magic,0,clr);
    if(tk>0) {
        g_st.lastTicket=tk;
        g_st.waitingForClose=true;
        g_dayTrades++;
        g_trades++;
        LogMsg(StringFormat("OPEN L%d %s Tk:%d Lot:%.2f (base=%.2f x%.3f) @%.5f SL:%.5f TP:%.5f",
            g_st.streak,dir,tk,lots,baseLot,mult,pr,sl,tp),true);
    } else {
        LogMsg(StringFormat("OPEN ERR:%d",GetLastError()),true);
    }
}

// ============================================================================
// SIGNAL (identique aux autres EAs)
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
// LOT CALCULATION (base lot; pyramid multiplier applied in OpenTrade)
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
