//+------------------------------------------------------------------+
//|                                    PureReverse75_v3.mq4          |
//|           STRATÉGIE PURE: 1 Reverse = Récupération 75%          |
//|                                                                  |
//|  v2 CHANGE: CheckSLHit() runs on every tick (no 1-bar delay)    |
//|                                                                  |
//|  v3 CHANGE (CRITICAL BUG FIX):                                  |
//|    OpenReverse() TP calculation was 10x too far on 5-digit      |
//|    brokers. Variable 'pipsNeeded' was actually TICKS, then      |
//|    multiplied by pip size (g_pt) instead of tick size.          |
//|    Fixed to use explicit ticks -> price conversion.             |
//|    Target 75% recovery is now actually ~8.6 pips (not ~86).    |
//+------------------------------------------------------------------+
#property copyright "Pure Reverse System"
#property version   "3.00"
#property strict
#property description "Pure Reverse 75% v3 - Instant REV + TP bug fix"

// ============================================================================
// INPUTS
// ============================================================================

input group "=== SIGNAL ==="
input int    Inp_EMA_Period      = 200;
input int    Inp_MACD_Fast       = 12;
input int    Inp_MACD_Slow       = 26;
input int    Inp_RSI_Period      = 14;

input group "=== TRADE INITIAL ==="
input int    Inp_ATR_Period      = 14;
input double Inp_SL_Mult         = 1.5;     // SL en × ATR
input double Inp_TP_Mult         = 2.0;     // TP en × ATR  
input double Inp_RiskPct         = 1.0;     // Risk %

input group "=== REVERSE (75% Recovery) ==="
input bool   Inp_UseReverse      = true;
input double Inp_RevMult         = 2.0;     // Lot ×2
input double Inp_Rev_RecoveryPct = 75.0;   // Récupérer 75% de la perte
input double Inp_Rev_SL_Mult     = 0.5;     // SL reverse (× ATR, petit)

input group "=== PROTECTION ==="
input double Inp_MaxDD           = 30.0;
input int    Inp_MaxDayTrades    = 20;

input group "=== TIME ==="
input bool   Inp_UseTime         = true;
input int    Inp_StartHr         = 8;
input int    Inp_EndHr           = 21;

input group "=== SYSTEM ==="
input int    Inp_Magic           = 112235;
input int    Inp_Slip            = 3;
input string Inp_Prefix          = "PR75v3";
input bool   Inp_Log             = true;

// ============================================================================
// STRUCTURES & GLOBALS
// ============================================================================

struct State {
    bool waitingForSL;      // En attente d'un SL pour reverse
    int lastTicket;
    double initialLoss;     // Perte du trade initial (si SL touché)
};

double g_pt;
int g_dig;
datetime g_lastBar = 0;
State g_st;

int g_trades = 0;
int g_reverses = 0;
int g_initialWins = 0;
int g_initialLosses = 0;
int g_reverseWins = 0;
int g_reverseLosses = 0;

datetime g_lastDay = 0;
int g_dayTrades = 0;

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

void LogMsg(string m,bool imp) {
    if(!Inp_Log && !imp) return;
    Print(StringFormat("%s %s %s",imp?"[!]":"[*]",TimeToString(TimeCurrent()),m));
}

// ============================================================================
// INIT / DEINIT
// ============================================================================

int OnInit() {
    g_dig=(int)MarketInfo(Symbol(),MODE_DIGITS);
    g_pt=(g_dig==3||g_dig==5)?MarketInfo(Symbol(),MODE_POINT)*10:MarketInfo(Symbol(),MODE_POINT);
    
    ResetState();
    
    LogMsg(StringFormat("=== PR75 READY | Rev:%s Mult:%.1f Recovery:%.0f%% ===",
        Inp_UseReverse?"ON":"OFF",Inp_RevMult,Inp_Rev_RecoveryPct),true);
        
    return INIT_SUCCEEDED;
}

void OnDeinit(const int& reason) {
    LogMsg(StringFormat("=== PR75 STOP | Trades:%d Revs:%d ===",g_trades,g_reverses),true);
}

// ============================================================================
// RESET
// ============================================================================

void ResetState() {
    g_st.waitingForSL=false;
    g_st.lastTicket=0;
    g_st.initialLoss=0;
}

// ============================================================================
// MAIN TICK
// ============================================================================

void OnTick() {
    // Reset journalier (tick level, cheap)
    string today=TimeToStr(TimeCurrent(),TIME_DATE);
    if(today!=g_lastDay) { g_dayTrades=0; g_lastDay=today; }

    if(!PreChecks()) return;

    // [TICK LEVEL] Instant SL detection -> immediate REV trigger
    // Was previously gated by IsNewBar() -> caused up to 1h delay on H1
    CheckSLHit();

    // [BAR LEVEL] Signal detection stays on new bar only
    if(!IsNewBar()) return;

    // Gestion positions
    ManagePos();

    // Nouveau signal si pas de position
    if(CountMyTrades()==0 && !g_st.waitingForSL) {
        if(g_dayTrades>=Inp_MaxDayTrades) return;

        int sig=GetSignal();
        if(sig==1) OpenInitial(OP_BUY);
        else if(sig==-1) OpenInitial(OP_SELL);
    }
}

// ============================================================================
// CHECK SI SL TOUCHÉ → DÉCLENCHE REVERSE
// ============================================================================

void CheckSLHit() {
    if(!Inp_UseReverse || !g_st.waitingForSL) return;
    if(g_st.lastTicket<=0) { ResetState(); return; }
    
    // Chercher le ticket dans l'historique (fermé)
    bool foundClosed=false;
    bool wasSL=false;
    double lossAmt=0;
    
    for(int i=OrdersHistoryTotal()-1; i>=0; i--) {
        if(!OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)) continue;
        if(OrderTicket()!=g_st.lastTicket || OrderSymbol()!=Symbol()) continue;
        
        foundClosed=true;
        
        // Calculer la perte réelle
        lossAmt=MathAbs(OrderProfit()+OrderSwap()+OrderCommission());
        
        // Déterminer si c'était un SL (perte)
        if(OrderProfit()+OrderSwap()+OrderCommission()<0) {
            wasSL=true;
            g_st.initialLoss=lossAmt;
        }
        break;
    }
    
    if(foundClosed) {
        if(wasSL) {
            // SL touché! Ouvrir le reverse
            OpenReverse(lossAmt);
        } else {
            // Le trade s'est fermé en profit (TP ou autre) → reset
            ResetState();
            g_initialWins++;
        }
    } else {
        // Vérifier si le ticket est encore ouvert
        bool stillOpen=false;
        for(int i=0;i<OrdersTotal();i++) {
            if(OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
                if(OrderTicket()==g_st.lastTicket && OrderSymbol()==Symbol()) stillOpen=true;
        }
        
        if(!stillOpen) {
            // Ticket introuvable → reset sécurité
            ResetState();
        }
    }
}

// ============================================================================
// OUVERTURE TRADE INITIAL
// ============================================================================

void OpenInitial(int type) {
    double atr=iATR(NULL,0,Inp_ATR_Period,1);
    double pr=(type==OP_BUY)?Ask:Bid;
    double sl,tp;
    
    if(type==OP_BUY) {
        sl=Norm(Ask-Inp_SL_Mult*atr);
        tp=Norm(Ask+Inp_TP_Mult*atr);
    } else {
        sl=Norm(Bid+Inp_SL_Mult*atr);
        tp=Norm(Bid-Inp_TP_Mult*atr);
    }
    
    double lots=CalcLots(sl);
    if(lots<=0) return;
    
    string dir=(type==OP_BUY)?"B":"S";
    string cmnt=StringFormat("%s-INIT-%s",Inp_Prefix,dir);
    color clr=(type==OP_BUY)?clrGreen:clrRed;
    
    int tk=OrderSend(Symbol(),type,lots,pr,Inp_Slip,sl,tp,cmnt,Inp_Magic,0,clr);
    
    if(tk>0) {
        g_st.lastTicket=tk;
        g_st.waitingForSL=true; // Attendre ce trade pour voir si SL touché
        g_st.initialLoss=0;
        
        g_dayTrades++;
        g_trades++;
        
        LogMsg(StringFormat("INIT %s Tkt:%d Lot:%.2f @%.5f SL:%.5f TP:%.5f",
            dir,tk,lots,pr,sl,tp),true);
    }
}

// ============================================================================
// OUVERTURE TRADE REVERSE (RÉCUPÉRATION 75%)
// ============================================================================

void OpenReverse(double initialLossAmount) {
    // Récupérer info du trade initial perdu
    int prevType=-1;
    double prevLots=0;
    double prevOpenPrice=0;
    double prevSL=0;
    
    for(int i=OrdersHistoryTotal()-1; i>=0; i--) {
        if(!OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)) continue;
        if(OrderTicket()!=g_st.lastTicket || OrderSymbol()!=Symbol()) continue;
        
        prevType=OrderType();
        prevLots=OrderLots();
        prevOpenPrice=OrderOpenPrice();
        prevSL=OrderStopLoss();
        break;
    }
    
    if(prevType==-1) { ResetState(); return; }
    
    // Type opposé
    int newType=(prevType==OP_BUY)?OP_SELL:OP_BUY;
    
    // Lot ×2
    double newLots=MinD(Norm(prevLots*Inp_RevMult), MarketInfo(Symbol(),MODE_MAXLOT));
    
    // Prix d'entrée = niveau du SL précédent (ou prix actuel proche)
    double entry=(newType==OP_BUY)?Ask:Bid;
    
    // ★ CALCUL TP: Récupérer X% de la perte initiale
    // v3 FIX: variable was mis-named 'pipsNeeded' but was actually TICKS.
    // Multiplying by g_pt (pip size) on 5-digit brokers made the TP 10x too far.
    // Fixed: compute ticks needed, convert to price via tickSize.
    double targetProfit=initialLossAmount * Inp_Rev_RecoveryPct / 100.0;

    double tickVal=MarketInfo(Symbol(),MODE_TICKVALUE);
    double tickSize=MarketInfo(Symbol(),MODE_TICKSIZE);
    if(tickVal<=0 || tickSize<=0) { ResetState(); return; }

    // Ticks of price movement required to realize targetProfit on newLots
    double ticksNeeded=targetProfit/(tickVal*newLots);
    double priceDistance=ticksNeeded*tickSize;

    double tp;
    if(newType==OP_BUY)
        tp=Norm(entry+priceDistance);
    else
        tp=Norm(entry-priceDistance);
    
    // SL: protection petite (au-delà de l'entrée)
    double atr=iATR(NULL,0,Inp_ATR_Period,1);
    double sl;
    if(newType==OP_BUY)
        sl=Norm(entry-Inp_Rev_SL_Mult*atr); // SL sous l'entrée
    else
        sl=Norm(entry+Inp_Rev_SL_Mult*atr); // SL au-dessus
    
    // Exécuter
    string dir=(newType==OP_BUY)?"B":"S";
    string cmnt=StringFormat("%s-REV-%s",Inp_Prefix,dir);
    color clr=(newType==OP_BUY)?clrBlue:clrOrange;
    
    int tk=OrderSend(Symbol(),newType,newLots,entry,Inp_Slip,sl,tp,cmnt,Inp_Magic,0,clr);
    
    if(tk>0) {
        g_st.lastTicket=tk;
        g_st.waitingForSL=false; // Plus de reverse après celui-ci
        g_st.initialLoss=0;
        
        g_dayTrades++;
        g_trades++;
        g_reverses++;
        
        LogMsg(StringFormat(
            "⚡ REV %s Tkt:%d Lot:%.2f @%.5f | InitialLoss:$%.2f TargetRecovery:$%.2f (%.0f%%)\n"+
            "    SL:%.5f TP:%.5f (TP dist: %.1f pts = %.1f pips)",
            dir,tk,newLots,entry,initialLossAmount,targetProfit,Inp_Rev_RecoveryPct,
            sl,tp,ticksNeeded,ticksNeeded*tickSize/g_pt),true);
            
    } else {
        LogMsg(StringFormat("REV ERR:%d",GetLastError()),true);
        ResetState();
    }
}

// ============================================================================
// SIGNAL
// ============================================================================

int GetSignal() {
    int sc=0;
    
    // EMA Trend
    double ema=iMA(NULL,0,Inp_EMA_Period,0,MODE_EMA,PRICE_CLOSE,1);
    if(Close[1]>ema) sc++; else if(Close[1]<ema) sc--;
    
    // MACD
    double macd=iMACD(NULL,0,Inp_MACD_Fast,Inp_MACD_Slow,9,PRICE_CLOSE,MODE_MAIN,1);
    double macdSig=iMACD(NULL,0,Inp_MACD_Fast,Inp_MACD_Slow,9,PRICE_CLOSE,MODE_SIGNAL,1);
    if(macd>macdSig && macd>0) sc++; else if(macd<macdSig && macd<0) sc--;
    
    // RSI
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

void ManagePos() {
    for(int i=OrdersTotal()-1;i>=0;i--) {
        if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
        if(OrderSymbol()!=Symbol()||OrderMagicNumber()!=Inp_Magic) continue;
        
        // Pas de trailing sur ce système simple
        // Les trades ont leur SL/TP fixe
    }
}

// ============================================================================
// LOT CALCULATION
// ============================================================================

double CalcLots(double slPrice) {
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
    
    // DD check
    double eq=AccountEquity();
    double bal=AccountBalance();
    if(bal>0 && ((bal-eq)/bal*100)>Inp_MaxDD) return false;
    
    return true;
}
//+------------------------------------------------------------------+