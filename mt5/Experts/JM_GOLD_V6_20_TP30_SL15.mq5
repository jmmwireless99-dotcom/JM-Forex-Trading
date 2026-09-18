//+------------------------------------------------------------------+
//| JM_GOLD_V6_20_TP30_SL15.mq5                                      |
//| V6.1 entries + fixed TP$30/SL$15 + two result-based adds only    |
//| NOT a new indicator set. Do not attach with V6.1 on same chart.  |
//+------------------------------------------------------------------+
#property strict
#property version   "6.20"
#property copyright "JM Tech Solution"
#property description "V6.20: V6.1 flow + TP30/SL15, block H21 SELL, easier score on ADX>=35 & M5ATR>=8"

#include <Trade/Trade.mqh>
CTrade trade;

input string InpSymbol              = "GOLD#";
input double InpLots                = 0.01;
input long   InpMagic               = 26091020;
input string InpMasterBuildTag      = "V6.20-TP30-SL15-H21BLOCK-STRONGTREND";

input int    InpM5FastEMA           = 20;
input int    InpM5SlowEMA           = 50;
input int    InpM5ADXPeriod         = 14;
input double InpMinADX              = 16.0;
input int    InpM1FastEMA           = 9;
input int    InpM1SlowEMA           = 21;
input int    InpM1RSIPeriod         = 14;

input int    InpM1ATRPeriod         = 14;
input double InpSmallRangeATRMax    = 0.70;
input double InpSmallBodyRatioMax   = 0.45;
input double InpBreakBufferATR      = 0.05;
input bool   InpRequireM1Flow       = true;
input bool   InpUseChopFilter        = true;
input double InpMinM5GapATR        = 0.06;
input double InpWeakADXLevel       = 20.0;
input double InpMinSmallRangeATR   = 0.15;
input double InpMaxSmallRangeATR2  = 0.80;
input bool   InpUseFlowScore       = true;
input int    InpMinFlowScore       = 3;
input bool   InpUseDynamicHourScore  = true;
input int    InpStrongHourScoreAdj  = -1;
input int    InpWeakHourScoreAdj    = 1;
input int    InpToxicHourScoreAdj   = 2;
input bool   InpUseDirectionalRouter = true;
input int    InpOppositeDirPenalty  = 1;
input int    InpDefensivePenalty    = 2;
input int    InpPreferredBonus      = -1;
input bool   InpUseProfitZoneRouter  = true;
input int    InpProfitZoneBonus     = -1;
input int    InpLossZonePenalty     = 2;

input double InpBuyRSIMin           = 46.0;
input double InpBuyRSIMax           = 68.0;
input double InpSellRSIMin          = 32.0;
input double InpSellRSIMax          = 54.0;

input bool   InpUseUsdTargets       = true;
input double InpQuietTargetUsd      = 30.0;
input double InpNormalTargetUsd     = 30.0;
input double InpStrongTargetUsd     = 30.0;
input double InpM1AtrQuiet          = 1.20;
input double InpM1AtrStrong         = 3.00;
input double InpRewardRisk          = 2.00;      // 30/15 = 1:2 (reference)
input bool   InpUseFixedSLUsd        = true;
input double InpFixedSLUsd           = 15.0;

// V6.20 — from YOUR TP30/SL15 journal. Not new indicators.
input bool   InpBlockH21Sell         = true;      // H21 SELL: 41 trades, 46% WR, −$263 (avg win ~$6)
input bool   InpUseStrongTrendBoost  = true;      // ADX>=35 + M5ATR>=8 made +$525 @ 49.3% WR
input double InpStrongTrendADX       = 35.0;
input double InpStrongTrendM5Atr     = 8.0;
input int    InpStrongTrendScoreAdj  = -1;        // easier entry in that pocket only

input int    InpMinSecondsBetween   = 20;
input int    InpMaxSpreadPoints     = 0;
input bool   InpAllowBuy            = true;
input bool   InpAllowSell           = true;
input bool   InpShowPanel           = true;
input bool   InpPrintAnalyzer       = false;
input bool   InpPrintSLHourAnalyzer  = false;
input bool   InpPrintMarketConditionAnalyzer = false;
input bool   InpUseStrictProfitHours = true;
input bool   InpUseProfitHourRouter = true;
input bool   InpKeepBothAtNeutral    = true;
input bool   InpUseV38Refinement      = true;
input bool   InpUseSafeSessionAB       = true;
input bool   InpBlockH17BuyOnly        = true;
input bool   InpBlockH16H17All       = true;
input int    InpABAsiaStartHour      = 0;
input int    InpABAsiaEndHour        = 7;
input int    InpABEuropeStartHour    = 7;
input int    InpABEuropeEndHour      = 15;
input int    InpABUSStartHour        = 15;
input int    InpABUSEndHour          = 24;

string g_symbol;
int hM5Fast=INVALID_HANDLE, hM5Slow=INVALID_HANDLE, hM5ADX=INVALID_HANDLE, hM5ATR=INVALID_HANDLE;
int hM1Fast=INVALID_HANDLE, hM1Slow=INVALID_HANDLE, hM1RSI=INVALID_HANDLE, hM1ATR=INVALID_HANDLE;
datetime g_lastEntryTime=0;
datetime g_lastSignalBar=0;
string g_status="Starting";

bool HasOpenPosition()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(!PositionSelectByTicket(t)) continue;
      string psym=PositionGetString(POSITION_SYMBOL);
      long   pmagic=PositionGetInteger(POSITION_MAGIC);
      if(psym==g_symbol && pmagic==InpMagic)
         return true;
   }
   return false;
}

bool SpreadOK()
{
   if(InpMaxSpreadPoints<=0) return true;
   MqlTick q; if(!SymbolInfoTick(g_symbol,q)) return false;
   return ((q.ask-q.bid)/SymbolInfoDouble(g_symbol,SYMBOL_POINT) <= InpMaxSpreadPoints);
}

double MoneyToPriceDistance(double money,double lots)
{
   double ts=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_SIZE);
   double tv=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_VALUE);
   if(money<=0 || lots<=0 || ts<=0 || tv<=0) return 0.0;
   return (money*ts)/(tv*lots);
}

double TargetUsd(double atr)
{
   // V6.15/V6.20 controlled 1:2: fixed TP $30 every trade.
   return InpNormalTargetUsd;
}

double RespectStops(double d)
{
   long lvl=SymbolInfoInteger(g_symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double minD=lvl*SymbolInfoDouble(g_symbol,SYMBOL_POINT);
   return MathMax(d,minD);
}

bool Read1(int handle,int shift,double &v)
{
   double b[1];
   if(CopyBuffer(handle,0,shift,1,b)!=1) return false;
   v=b[0];
   return true;
}

int M5Bias(double &adx,double &gapATR)
{
   double f,s,m5atr;
   if(!Read1(hM5Fast,1,f) || !Read1(hM5Slow,1,s) ||
      !Read1(hM5ADX,1,adx) || !Read1(hM5ATR,1,m5atr))
      return 0;
   if(m5atr<=0.0) return 0;
   gapATR=MathAbs(f-s)/m5atr;
   if(adx<InpMinADX) return 0;
   if(InpUseChopFilter && gapATR<InpMinM5GapATR && adx<InpWeakADXLevel)
      return 0;
   if(f>s) return 1;
   if(f<s) return -1;
   return 0;
}

bool GetSmallCandle(MqlRates &bar,double &atr,double &bodyRatio,double &rangeAtr)
{
   MqlRates r[1];
   if(CopyRates(g_symbol,PERIOD_M1,1,1,r)!=1) return false;
   bar=r[0];
   if(!Read1(hM1ATR,1,atr) || atr<=0) return false;
   double range=bar.high-bar.low;
   if(range<=0) return false;
   bodyRatio=MathAbs(bar.close-bar.open)/range;
   rangeAtr=range/atr;
   return (rangeAtr>=InpMinSmallRangeATR && rangeAtr<=InpMaxSmallRangeATR2 && bodyRatio<=InpSmallBodyRatioMax);
}

int M1Flow(double &rsi)
{
   double f,s;
   if(!Read1(hM1Fast,1,f) || !Read1(hM1Slow,1,s) || !Read1(hM1RSI,1,rsi))
      return 0;
   if(f>s) return 1;
   if(f<s) return -1;
   return 0;
}
int FlowScore(int bias,int flow,double adx,double gapATR,double rsi,double bodyRatio,double rangeAtr)
{
   int score=0;
   if(flow==bias) score++;
   if(adx>=InpWeakADXLevel) score++;
   if(gapATR>=InpMinM5GapATR) score++;
   if(rangeAtr>=0.25 && rangeAtr<=0.65) score++;
   if(bias>0)
   {
      if(rsi>=48.0 && rsi<=64.0) score++;
   }
   else
   {
      if(rsi>=36.0 && rsi<=52.0) score++;
   }
   if(bodyRatio>=0.12 && bodyRatio<=0.40) score++;
   return score;
}

enum HourRoute
{
   ROUTE_BOTH=0,
   ROUTE_BUY=1,
   ROUTE_SELL=2,
   ROUTE_DEFENSIVE=3
};

HourRoute GetHourRoute(const int hour)
{
   if(hour==1 || hour==2 || hour==12)
      return ROUTE_BOTH;
   if(hour==5 || hour==8 || hour==10 || hour==13 ||
      hour==16 || hour==17 || hour==20 || hour==21)
      return ROUTE_SELL;
   if(hour==7 || hour==23)
      return ROUTE_BUY;
   if(hour==3 || hour==4 || hour==6 || hour==9 || hour==11 ||
      hour==14 || hour==15 || hour==18 || hour==19 || hour==22)
      return ROUTE_DEFENSIVE;
   return ROUTE_BOTH;
}

int ProfitZoneAdjustment(const int dir,const int hour)
{
   if(!InpUseProfitZoneRouter)
      return 0;
   if(dir>0)
   {
      if(hour==4 || hour==7 || hour==23)
         return InpProfitZoneBonus;
      if(hour==5 || hour==6 || hour==10 || hour==12 ||
         hour==13 || hour==15 || hour==19 || hour==20)
         return InpLossZonePenalty;
   }
   else
   {
      if(hour==1 || hour==2 || hour==5 || hour==8 ||
         hour==12 || hour==13 || hour==16 || hour==17 ||
         hour==20 || hour==21)
         return InpProfitZoneBonus;
      if(hour==3 || hour==6 || hour==9 || hour==11 ||
         hour==15 || hour==18 || hour==19 || hour==22 || hour==23)
         return InpLossZonePenalty;
   }
   return 0;
}

int DynamicRequiredScore(const int dir,const int hour)
{
   int need=InpMinFlowScore;
   if(InpUseDynamicHourScore)
   {
      if(dir>0)
      {
         if(hour==7 || hour==23)
            need += InpStrongHourScoreAdj;
         if(hour==5 || hour==13 || hour==19 || hour==20)
            need += InpWeakHourScoreAdj;
      }
      else
      {
         if(hour==5 || hour==8 || hour==10 || hour==13 ||
            hour==16 || hour==17 || hour==20 || hour==21)
            need += InpStrongHourScoreAdj;
         if(hour==11 || hour==18 || hour==19 || hour==22)
            need += InpWeakHourScoreAdj;
      }
   }
   if(InpUseDirectionalRouter)
   {
      HourRoute route=GetHourRoute(hour);
      if(route==ROUTE_DEFENSIVE)
         need += InpDefensivePenalty;
      else if(route==ROUTE_BUY)
      {
         if(dir>0) need += InpPreferredBonus;
         else      need += InpOppositeDirPenalty;
      }
      else if(route==ROUTE_SELL)
      {
         if(dir<0) need += InpPreferredBonus;
         else      need += InpOppositeDirPenalty;
      }
   }
   need += ProfitZoneAdjustment(dir,hour);
   if(need<1) need=1;
   if(need>6) need=6;
   return need;
}

bool OpenTrade(int dir,double atr,string reason)
{
   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return false;
   double target=InpUseUsdTargets ? TargetUsd(atr) : InpNormalTargetUsd;
   double risk=(InpRewardRisk>0 ? target/InpRewardRisk : target);
   if(InpUseFixedSLUsd && InpFixedSLUsd>0.0)
      risk=InpFixedSLUsd;

   double tpDist=MoneyToPriceDistance(target,InpLots);
   double slDist=MoneyToPriceDistance(risk,InpLots);
   if(tpDist<=0 || slDist<=0) return false;

   tpDist=RespectStops(tpDist);
   slDist=RespectStops(slDist);
   int dg=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);
   double sl,tp;
   bool ok=false;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFillingBySymbol(g_symbol);
   if(dir>0)
   {
      sl=NormalizeDouble(q.ask-slDist,dg);
      tp=NormalizeDouble(q.ask+tpDist,dg);
      ok=trade.Buy(InpLots,g_symbol,0.0,sl,tp,reason);
   }
   else
   {
      sl=NormalizeDouble(q.bid+slDist,dg);
      tp=NormalizeDouble(q.bid-tpDist,dg);
      ok=trade.Sell(InpLots,g_symbol,0.0,sl,tp,reason);
   }
   if(ok)
   {
      g_lastEntryTime=TimeCurrent();
      g_status=StringFormat("%s OPEN | TP~$%.2f Risk~$%.2f",
                            dir>0?"BUY":"SELL",target,risk);
      Print(g_status," | ",reason);
   }
   else
   {
      g_status="Order failed: "+trade.ResultRetcodeDescription();
      Print(g_status);
   }
   return ok;
}

int OnInit()
{
   g_symbol=(InpSymbol=="" ? _Symbol : InpSymbol);
   if(!SymbolSelect(g_symbol,true)) return INIT_FAILED;
   hM5Fast=iMA(g_symbol,PERIOD_M5,InpM5FastEMA,0,MODE_EMA,PRICE_CLOSE);
   hM5Slow=iMA(g_symbol,PERIOD_M5,InpM5SlowEMA,0,MODE_EMA,PRICE_CLOSE);
   hM5ADX=iADX(g_symbol,PERIOD_M5,InpM5ADXPeriod);
   hM5ATR=iATR(g_symbol,PERIOD_M5,14);
   hM1Fast=iMA(g_symbol,PERIOD_M1,InpM1FastEMA,0,MODE_EMA,PRICE_CLOSE);
   hM1Slow=iMA(g_symbol,PERIOD_M1,InpM1SlowEMA,0,MODE_EMA,PRICE_CLOSE);
   hM1RSI=iRSI(g_symbol,PERIOD_M1,InpM1RSIPeriod,PRICE_CLOSE);
   hM1ATR=iATR(g_symbol,PERIOD_M1,InpM1ATRPeriod);
   if(hM5Fast==INVALID_HANDLE || hM5Slow==INVALID_HANDLE || hM5ADX==INVALID_HANDLE ||
      hM5ATR==INVALID_HANDLE || hM1Fast==INVALID_HANDLE || hM1Slow==INVALID_HANDLE || hM1RSI==INVALID_HANDLE ||
      hM1ATR==INVALID_HANDLE)
      return INIT_FAILED;
   trade.SetExpertMagicNumber(InpMagic);
   Print("=== ",InpMasterBuildTag," | Symbol=",g_symbol," | Lot=",DoubleToString(InpLots,2),
         " | TP$",DoubleToString(InpNormalTargetUsd,0)," SL$",DoubleToString(InpFixedSLUsd,0),
         " | H21SELL=",(InpBlockH21Sell?"ON":"off"),
         " | StrongTrendBoost=",(InpUseStrongTrendBoost?"ON":"off")," ===");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hM5Fast!=INVALID_HANDLE) IndicatorRelease(hM5Fast);
   if(hM5Slow!=INVALID_HANDLE) IndicatorRelease(hM5Slow);
   if(hM5ADX!=INVALID_HANDLE) IndicatorRelease(hM5ADX);
   if(hM5ATR!=INVALID_HANDLE) IndicatorRelease(hM5ATR);
   if(hM1Fast!=INVALID_HANDLE) IndicatorRelease(hM1Fast);
   if(hM1Slow!=INVALID_HANDLE) IndicatorRelease(hM1Slow);
   if(hM1RSI!=INVALID_HANDLE) IndicatorRelease(hM1RSI);
   if(hM1ATR!=INVALID_HANDLE) IndicatorRelease(hM1ATR);
   Comment("");
}

bool StrictProfitHourAllowed(const int dir,const int hour)
{
   if(!InpUseStrictProfitHours)
      return true;
   if(dir<0)
   {
      if(hour==1 || hour==2 || hour==5 || hour==8 ||
         hour==12 || hour==16 || hour==17 || hour==20 || hour==21)
         return true;
      return false;
   }
   if(dir>0)
      return (hour==23);
   return false;
}

bool ProfitHourAllowed(const int dir,const int hour)
{
   if(!InpUseProfitHourRouter)
      return true;
   if(dir>0)
   {
      if(hour==5 || hour==6 || hour==10 || hour==12 ||
         hour==13 || hour==14 || hour==15 || hour==19 || hour==20)
         return false;
      if(InpUseV38Refinement)
      {
         if(hour==4 || hour==11 || hour==16 || hour==18 || hour==22)
            return false;
      }
      return true;
   }
   if(dir<0)
   {
      if(hour==3 || hour==6 || hour==9 || hour==11 ||
         hour==15 || hour==18 || hour==19 || hour==22 || hour==23)
         return false;
      if(InpUseV38Refinement)
      {
         if(hour==7 || hour==10 || hour==13 || hour==14)
            return false;
      }
      return true;
   }
   return false;
}

enum ABSess
{
   AB_ASIA=0,
   AB_EUROPE=1,
   AB_US=2
};

ABSess ABSessionByHour(const int hour)
{
   if(hour>=InpABAsiaStartHour && hour<InpABAsiaEndHour)
      return AB_ASIA;
   if(hour>=InpABEuropeStartHour && hour<InpABEuropeEndHour)
      return AB_EUROPE;
   return AB_US;
}

bool SafeABDirectionAllowed(const int dir,const int hour)
{
   if(!InpUseSafeSessionAB)
      return true;
   ABSess s=ABSessionByHour(hour);
   if(s==AB_ASIA || s==AB_EUROPE)
      return (dir<0);
   return true;
}

string JM_SideAnalyzerLine(const int dir,
                           const int hour,
                           const int bias,
                           const int flow,
                           const bool haveSmall,
                           const double adx,
                           const double gapATR,
                           const double rsi,
                           const double bodyRatio,
                           const double rangeAtr,
                           const double atr,
                           const MqlRates &small)
{
   if(InpBlockH16H17All && (hour==16 || hour==17))
      return "MALI  V6.1 H16/H17 hard block";
   if(InpBlockH21Sell && dir<0 && hour==21)
      return "MALI  V6.20 H21 SELL block";
   if(InpBlockH17BuyOnly && dir>0 && hour==17)
      return "MALI  V4.2 H17 BUY block";
   if(!StrictProfitHourAllowed(dir,hour))
      return "MALI  strict-hour (BUY only H23 / SELL whitelist)";
   if(!ProfitHourAllowed(dir,hour))
      return "MALI  hour router reject";
   if(!SafeABDirectionAllowed(dir,hour))
      return "MALI  SAFE-AB (Asia/Europe SELL only)";
   if(bias==0)
      return "MALI  no M5 flow / ADX weak";
   if(bias!=dir)
      return "MALI  against M5 bias";
   if(InpRequireM1Flow && flow!=bias)
      return "MALI  M1 flow disagrees with M5";
   if(!haveSmall)
      return "WAIT  no M1 small candle";

   int score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
   int need=DynamicRequiredScore(dir,hour);
   if(InpUseStrongTrendBoost)
   {
      double m5atr=0.0;
      if(Read1(hM5ATR,1,m5atr) && adx>=InpStrongTrendADX && m5atr>=InpStrongTrendM5Atr)
      {
         need += InpStrongTrendScoreAdj;
         if(need<1) need=1;
      }
   }
   if(InpUseFlowScore && score<need)
      return StringFormat("MALI  score %d < need %d",score,need);

   if(dir>0 && (rsi<InpBuyRSIMin || rsi>InpBuyRSIMax))
      return StringFormat("MALI  RSI %.1f outside BUY %.0f-%.0f",rsi,InpBuyRSIMin,InpBuyRSIMax);
   if(dir<0 && (rsi<InpSellRSIMin || rsi>InpSellRSIMax))
      return StringFormat("MALI  RSI %.1f outside SELL %.0f-%.0f",rsi,InpSellRSIMin,InpSellRSIMax);

   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q))
      return "WAIT  no tick";
   double buffer=atr*InpBreakBufferATR;
   bool brk=(dir>0 ? (q.ask>small.high+buffer) : (q.bid<small.low-buffer));
   if(!brk)
      return StringFormat("WAIT  score %d/%d — no breakout yet",score,need);
   return StringFormat("OK    score %d/%d — entry ready",score,need);
}

void LiveAnalyzerTick()
{
   if(!InpShowPanel)
      return;

   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   int hour=tm.hour;

   double adx=0.0,gapATR=0.0,rsi=0.0;
   int bias=M5Bias(adx,gapATR);
   int flow=M1Flow(rsi);

   MqlRates small;
   ZeroMemory(small);
   double atr=0.0,bodyRatio=0.0,rangeAtr=0.0;
   bool haveSmall=GetSmallCandle(small,atr,bodyRatio,rangeAtr);

   int score=0,need=InpMinFlowScore;
   if(bias!=0)
   {
      score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
      need=DynamicRequiredScore(bias,hour);
      if(InpUseStrongTrendBoost)
      {
         double m5atr=0.0;
         if(Read1(hM5ATR,1,m5atr) && adx>=InpStrongTrendADX && m5atr>=InpStrongTrendM5Atr)
         {
            need += InpStrongTrendScoreAdj;
            if(need<1) need=1;
         }
      }
   }

   string h16=(InpBlockH16H17All && (hour==16 || hour==17)) ? "MALI" : "OK";
   string buyLine=JM_SideAnalyzerLine(1,hour,bias,flow,haveSmall,adx,gapATR,rsi,bodyRatio,rangeAtr,atr,small);
   string sellLine=JM_SideAnalyzerLine(-1,hour,bias,flow,haveSmall,adx,gapATR,rsi,bodyRatio,rangeAtr,atr,small);

   Comment("JM V6.20 TP30/SL15 ANALYZER  ",InpMasterBuildTag,"\n",
           "Hour H",IntegerToString(hour),
           "  route ",IntegerToString((int)GetHourRoute(hour)),
           "  H16/H17 ",h16,"\n",
           "M5 ",(bias>0?"BUY":bias<0?"SELL":"NONE"),
           "  ADX ",DoubleToString(adx,1),
           "  GapATR ",DoubleToString(gapATR,3),"\n",
           "M1 ",(flow>0?"BUY":flow<0?"SELL":"FLAT"),
           "  RSI ",DoubleToString(rsi,1),
           "  small ",(haveSmall?"YES":"NO"),
           "  score ",IntegerToString(score),"/",IntegerToString(need),"\n",
           "BUY  ",buyLine,"\n",
           "SELL ",sellLine,"\n",
           "Status: ",g_status);
}

void OnTick()
{
   LiveAnalyzerTick();
   if(HasOpenPosition()) return;
   if(!SpreadOK()) return;
   if((TimeCurrent()-g_lastEntryTime)<InpMinSecondsBetween) return;

   MqlRates small;
   double atr,bodyRatio,rangeAtr;
   if(!GetSmallCandle(small,atr,bodyRatio,rangeAtr))
   {
      g_status="Waiting for M1 small candle";
      LiveAnalyzerTick();
      return;
   }

   if(small.time==g_lastSignalBar) return;

   double adx=0.0,rsi=0.0,gapATR=0.0;
   int bias=M5Bias(adx,gapATR);
   if(bias==0)
   {
      g_status="No M5 flow / ADX weak";
      LiveAnalyzerTick();
      return;
   }

   int flow=M1Flow(rsi);
   if(InpRequireM1Flow && flow!=bias)
   {
      g_status="M1 flow disagrees with M5";
      LiveAnalyzerTick();
      return;
   }

   int flowScore=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);

   MqlDateTime tmNow;
   TimeToStruct(TimeCurrent(),tmNow);

   if(InpBlockH16H17All && (tmNow.hour==16 || tmNow.hour==17))
   {
      g_status=StringFormat("V6.1 HARD BLOCK H%02d ALL",tmNow.hour);
      LiveAnalyzerTick();
      return;
   }

   if(InpBlockH21Sell && bias<0 && tmNow.hour==21)
   {
      g_status="V6.20 HARD BLOCK H21 SELL";
      LiveAnalyzerTick();
      return;
   }

   if(!StrictProfitHourAllowed(bias,tmNow.hour))
   {
      g_status=StringFormat("V6.0 strict-hour reject H%02d %s",tmNow.hour,bias>0?"BUY":"SELL");
      LiveAnalyzerTick();
      return;
   }
   int requiredScore=DynamicRequiredScore(bias,tmNow.hour);

   if(InpUseStrongTrendBoost)
   {
      double m5atr=0.0;
      if(Read1(hM5ATR,1,m5atr) && adx>=InpStrongTrendADX && m5atr>=InpStrongTrendM5Atr)
      {
         requiredScore += InpStrongTrendScoreAdj;
         if(requiredScore<1) requiredScore=1;
      }
   }

   if(InpUseFlowScore && flowScore<requiredScore)
   {
      g_status=StringFormat("Flow score %d < dynamic %d",flowScore,requiredScore);
      LiveAnalyzerTick();
      return;
   }

   MqlDateTime routeTm;
   TimeToStruct(TimeCurrent(),routeTm);

   if(!ProfitHourAllowed(bias,routeTm.hour))
   {
      g_status=StringFormat("Hour router reject H%02d %s",routeTm.hour,bias>0?"BUY":"SELL");
      LiveAnalyzerTick();
      return;
   }

   if(!SafeABDirectionAllowed(bias,routeTm.hour))
   {
      g_status=StringFormat("SAFE-AB reject H%02d %s",routeTm.hour,bias>0?"BUY":"SELL");
      LiveAnalyzerTick();
      return;
   }

   if(InpBlockH17BuyOnly && bias>0 && routeTm.hour==17)
   {
      g_status="V4.2 reject H17 BUY";
      LiveAnalyzerTick();
      return;
   }

   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return;

   double buffer=atr*InpBreakBufferATR;
   bool buyBreak=(q.ask > small.high + buffer);
   bool sellBreak=(q.bid < small.low  - buffer);

   if(bias>0 && InpAllowBuy && buyBreak && rsi>=InpBuyRSIMin && rsi<=InpBuyRSIMax)
   {
      g_lastSignalBar=small.time;
      OpenTrade(1,atr,StringFormat("SMALL_FLOW BUY | Score=%d Need=%d Route=%d ADX=%.1f GapATR=%.3f RSI=%.1f Body=%.2f RangeATR=%.2f",
                                   flowScore,requiredScore,(int)GetHourRoute(tmNow.hour),adx,gapATR,rsi,bodyRatio,rangeAtr));
      LiveAnalyzerTick();
      return;
   }

   if(bias<0 && InpAllowSell && sellBreak && rsi>=InpSellRSIMin && rsi<=InpSellRSIMax)
   {
      g_lastSignalBar=small.time;
      OpenTrade(-1,atr,StringFormat("SMALL_FLOW SELL | Score=%d Need=%d Route=%d ADX=%.1f GapATR=%.3f RSI=%.1f Body=%.2f RangeATR=%.2f",
                                    flowScore,requiredScore,(int)GetHourRoute(tmNow.hour),adx,gapATR,rsi,bodyRatio,rangeAtr));
      LiveAnalyzerTick();
      return;
   }

   LiveAnalyzerTick();
}
bool V48ReadAt(int handle,const datetime t,const ENUM_TIMEFRAMES tf,const int closedOffset,double &v)
{
   int sh=iBarShift(g_symbol,tf,t,false);
   if(sh<0) return false;
   sh+=closedOffset;
   double b[1];
   if(CopyBuffer(handle,0,sh,1,b)!=1) return false;
   v=b[0];
   return true;
}

bool V48EntryMetrics(const datetime entryTime,
                     double &adx,double &m5atr,double &gapATR,double &slopeATR,
                     double &m1atr,double &rsi,double &body,double &rangeATR)
{
   int m5=iBarShift(g_symbol,PERIOD_M5,entryTime,false);
   int m1=iBarShift(g_symbol,PERIOD_M1,entryTime,false);
   if(m5<0 || m1<0) return false;
   int s5=m5+1;
   int s1=m1+1;
   double fast[1],slow[1],adxv[1],atr5[1],fastPast[1],atr1[1],rsiv[1];
   if(CopyBuffer(hM5Fast,0,s5,1,fast)!=1) return false;
   if(CopyBuffer(hM5Slow,0,s5,1,slow)!=1) return false;
   if(CopyBuffer(hM5ADX,0,s5,1,adxv)!=1) return false;
   if(CopyBuffer(hM5ATR,0,s5,1,atr5)!=1) return false;
   if(CopyBuffer(hM5Fast,0,s5+3,1,fastPast)!=1) return false;
   if(CopyBuffer(hM1ATR,0,s1,1,atr1)!=1) return false;
   if(CopyBuffer(hM1RSI,0,s1,1,rsiv)!=1) return false;
   MqlRates r[1];
   if(CopyRates(g_symbol,PERIOD_M1,s1,1,r)!=1) return false;
   if(atr5[0]<=0 || atr1[0]<=0) return false;
   double range=r[0].high-r[0].low;
   if(range<=0) return false;
   adx=adxv[0];
   m5atr=atr5[0];
   gapATR=MathAbs(fast[0]-slow[0])/atr5[0];
   slopeATR=MathAbs(fast[0]-fastPast[0])/atr5[0];
   m1atr=atr1[0];
   rsi=rsiv[0];
   body=MathAbs(r[0].close-r[0].open)/range;
   rangeATR=range/atr1[0];
   return true;
}

int V48ADXBucket(const double v) { if(v<25.0) return 0; if(v<35.0) return 1; return 2; }
string V48ADXName(const int i) { if(i==0) return "ADX<25"; if(i==1) return "ADX25-35"; return "ADX>=35"; }
int V48ATRBucket(const double v) { if(v<4.0) return 0; if(v<8.0) return 1; return 2; }
string V48ATRName(const int i) { if(i==0) return "M5ATR<4"; if(i==1) return "M5ATR4-8"; return "M5ATR>=8"; }
int V48GapBucket(const double v) { if(v<0.25) return 0; if(v<0.75) return 1; return 2; }
string V48GapName(const int i) { if(i==0) return "GapATR<0.25"; if(i==1) return "GapATR0.25-0.75"; return "GapATR>=0.75"; }
int V48BodyBucket(const double v) { if(v<0.20) return 0; if(v<0.50) return 1; return 2; }
string V48BodyName(const int i) { if(i==0) return "Body<0.20"; if(i==1) return "Body0.20-0.50"; return "Body>=0.50"; }
int V48RangeBucket(const double v) { if(v<0.40) return 0; if(v<0.80) return 1; return 2; }
string V48RangeName(const int i) { if(i==0) return "RangeATR<0.40"; if(i==1) return "RangeATR0.40-0.80"; return "RangeATR>=0.80"; }

void V48PrintBucket(const string title,const int &t[],const int &w[],const double &p[])
{
   Print(title);
   for(int i=0;i<ArraySize(t);i++)
   {
      if(t[i]<=0) continue;
      double wr=100.0*w[i]/t[i];
      string nm="";
      if(StringFind(title,"ADX")>=0) nm=V48ADXName(i);
      else if(StringFind(title,"M5 ATR")>=0) nm=V48ATRName(i);
      else if(StringFind(title,"GAP")>=0) nm=V48GapName(i);
      else if(StringFind(title,"BODY")>=0) nm=V48BodyName(i);
      else nm=V48RangeName(i);
      PrintFormat("%s | T=%d W=%d L=%d WR=%.1f%% PnL=%.2f",
                  nm,t[i],w[i],t[i]-w[i],wr,p[i]);
   }
}

void PrintV48MarketConditionAnalyzer()
{
   if(!InpPrintMarketConditionAnalyzer) return;
   if(!HistorySelect(0,TimeCurrent())) return;
   int adxT[3],adxW[3],atrT[3],atrW[3],gapT[3],gapW[3],bodyT[3],bodyW[3],rangeT[3],rangeW[3];
   double adxP[3],atrP[3],gapP[3],bodyP[3],rangeP[3];
   ArrayInitialize(adxT,0); ArrayInitialize(adxW,0); ArrayInitialize(adxP,0.0);
   ArrayInitialize(atrT,0); ArrayInitialize(atrW,0); ArrayInitialize(atrP,0.0);
   ArrayInitialize(gapT,0); ArrayInitialize(gapW,0); ArrayInitialize(gapP,0.0);
   ArrayInitialize(bodyT,0); ArrayInitialize(bodyW,0); ArrayInitialize(bodyP,0.0);
   ArrayInitialize(rangeT,0); ArrayInitialize(rangeW,0); ArrayInitialize(rangeP,0.0);
   int comboT[3][3],comboW[3][3];
   double comboP[3][3];
   ArrayInitialize(comboT,0); ArrayInitialize(comboW,0); ArrayInitialize(comboP,0.0);
   int hBuyT[24],hBuyW[24],hSellT[24],hSellW[24];
   double hBuyP[24],hSellP[24];
   ArrayInitialize(hBuyT,0); ArrayInitialize(hBuyW,0); ArrayInitialize(hBuyP,0.0);
   ArrayInitialize(hSellT,0); ArrayInitialize(hSellW,0); ArrayInitialize(hSellP,0.0);
   int n=HistoryDealsTotal();
   int matched=0,missed=0;
   for(int i=0;i<n;i++)
   {
      ulong out=HistoryDealGetTicket(i);
      if(out==0) continue;
      if(HistoryDealGetString(out,DEAL_SYMBOL)!=g_symbol) continue;
      if(HistoryDealGetInteger(out,DEAL_MAGIC)!=InpMagic) continue;
      long ek=HistoryDealGetInteger(out,DEAL_ENTRY);
      if(ek!=DEAL_ENTRY_OUT && ek!=DEAL_ENTRY_OUT_BY) continue;
      ulong pid=(ulong)HistoryDealGetInteger(out,DEAL_POSITION_ID);
      datetime et=0;
      long typ=-1;
      for(int j=i-1;j>=0;j--)
      {
         ulong di=HistoryDealGetTicket(j);
         if(di==0) continue;
         if((ulong)HistoryDealGetInteger(di,DEAL_POSITION_ID)!=pid) continue;
         if(HistoryDealGetInteger(di,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
         et=(datetime)HistoryDealGetInteger(di,DEAL_TIME);
         typ=HistoryDealGetInteger(di,DEAL_TYPE);
         break;
      }
      if(et==0) { missed++; continue; }
      double adx,m5atr,gap,slope,m1atr,rsi,body,rangeATR;
      if(!V48EntryMetrics(et,adx,m5atr,gap,slope,m1atr,rsi,body,rangeATR))
      { missed++; continue; }
      double pnl=HistoryDealGetDouble(out,DEAL_PROFIT)
                +HistoryDealGetDouble(out,DEAL_SWAP)
                +HistoryDealGetDouble(out,DEAL_COMMISSION);
      bool win=(pnl>0.0);
      int ab=V48ADXBucket(adx);
      int tb=V48ATRBucket(m5atr);
      int gb=V48GapBucket(gap);
      int bb=V48BodyBucket(body);
      int rb=V48RangeBucket(rangeATR);
      adxT[ab]++; if(win) adxW[ab]++; adxP[ab]+=pnl;
      atrT[tb]++; if(win) atrW[tb]++; atrP[tb]+=pnl;
      gapT[gb]++; if(win) gapW[gb]++; gapP[gb]+=pnl;
      bodyT[bb]++; if(win) bodyW[bb]++; bodyP[bb]+=pnl;
      rangeT[rb]++; if(win) rangeW[rb]++; rangeP[rb]+=pnl;
      comboT[ab][tb]++; if(win) comboW[ab][tb]++; comboP[ab][tb]+=pnl;
      MqlDateTime tm;
      TimeToStruct(et,tm);
      if(typ==DEAL_TYPE_BUY)
      { hBuyT[tm.hour]++; if(win) hBuyW[tm.hour]++; hBuyP[tm.hour]+=pnl; }
      else if(typ==DEAL_TYPE_SELL)
      { hSellT[tm.hour]++; if(win) hSellW[tm.hour]++; hSellP[tm.hour]+=pnl; }
      matched++;
   }
   Print("=========== V6.0 POST-TEST MARKET CONDITION ANALYZER =========");
   PrintFormat("MATCHED=%d MISSED=%d",matched,missed);
   V48PrintBucket("--- ADX / TREND STRENGTH ---",adxT,adxW,adxP);
   V48PrintBucket("--- M5 ATR / VOLATILITY ---",atrT,atrW,atrP);
   V48PrintBucket("--- EMA GAP / STRUCTURE ---",gapT,gapW,gapP);
   V48PrintBucket("--- M1 BODY QUALITY ---",bodyT,bodyW,bodyP);
   V48PrintBucket("--- M1 RANGE / ATR ---",rangeT,rangeW,rangeP);
   Print("===============================================================");
}

double OnTester()
{
   if(!InpPrintAnalyzer && !InpPrintSLHourAnalyzer && !InpPrintMarketConditionAnalyzer) return 0.0;
   if(!HistorySelect(0,TimeCurrent())) return 0.0;
   int buyT[24],buyW[24],sellT[24],sellW[24];
   double buyP[24],sellP[24];
   int buyTP[24],buySL[24],sellTP[24],sellSL[24];
   int buyMaxSLStreak[24],sellMaxSLStreak[24];
   int buyCurSLStreak[24],sellCurSLStreak[24];
   double buyLossSum[24],sellLossSum[24];
   ArrayInitialize(buyT,0); ArrayInitialize(buyW,0);
   ArrayInitialize(sellT,0); ArrayInitialize(sellW,0);
   ArrayInitialize(buyP,0.0); ArrayInitialize(sellP,0.0);
   ArrayInitialize(buyTP,0); ArrayInitialize(buySL,0);
   ArrayInitialize(sellTP,0); ArrayInitialize(sellSL,0);
   ArrayInitialize(buyMaxSLStreak,0); ArrayInitialize(sellMaxSLStreak,0);
   ArrayInitialize(buyCurSLStreak,0); ArrayInitialize(sellCurSLStreak,0);
   ArrayInitialize(buyLossSum,0.0); ArrayInitialize(sellLossSum,0.0);
   int n=HistoryDealsTotal();
   for(int i=0;i<n;i++)
   {
      ulong d=HistoryDealGetTicket(i);
      if(d==0) continue;
      if(HistoryDealGetString(d,DEAL_SYMBOL)!=g_symbol) continue;
      if(HistoryDealGetInteger(d,DEAL_MAGIC)!=InpMagic) continue;
      long e=HistoryDealGetInteger(d,DEAL_ENTRY);
      if(e!=DEAL_ENTRY_OUT && e!=DEAL_ENTRY_OUT_BY) continue;
      ulong pid=(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID);
      datetime et=0;
      long typ=-1;
      for(int j=i-1;j>=0;j--)
      {
         ulong di=HistoryDealGetTicket(j);
         if(di==0) continue;
         if((ulong)HistoryDealGetInteger(di,DEAL_POSITION_ID)!=pid) continue;
         if(HistoryDealGetInteger(di,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
         et=(datetime)HistoryDealGetInteger(di,DEAL_TIME);
         typ=HistoryDealGetInteger(di,DEAL_TYPE);
         break;
      }
      if(et==0) continue;
      MqlDateTime tm;
      TimeToStruct(et,tm);
      int h=tm.hour;
      double pnl=HistoryDealGetDouble(d,DEAL_PROFIT)
                +HistoryDealGetDouble(d,DEAL_SWAP)
                +HistoryDealGetDouble(d,DEAL_COMMISSION);
      long reason=(long)HistoryDealGetInteger(d,DEAL_REASON);
      bool isTP=(reason==DEAL_REASON_TP);
      bool isSL=(reason==DEAL_REASON_SL);
      if(typ==DEAL_TYPE_BUY)
      {
         buyT[h]++; buyP[h]+=pnl;
         if(pnl>0.0) buyW[h]++;
         if(isTP) { buyTP[h]++; buyCurSLStreak[h]=0; }
         else if(isSL)
         {
            buySL[h]++; buyLossSum[h]+=pnl; buyCurSLStreak[h]++;
            if(buyCurSLStreak[h]>buyMaxSLStreak[h]) buyMaxSLStreak[h]=buyCurSLStreak[h];
         }
         else if(pnl>=0.0) buyCurSLStreak[h]=0;
      }
      else if(typ==DEAL_TYPE_SELL)
      {
         sellT[h]++; sellP[h]+=pnl;
         if(pnl>0.0) sellW[h]++;
         if(isTP) { sellTP[h]++; sellCurSLStreak[h]=0; }
         else if(isSL)
         {
            sellSL[h]++; sellLossSum[h]+=pnl; sellCurSLStreak[h]++;
            if(sellCurSLStreak[h]>sellMaxSLStreak[h]) sellMaxSLStreak[h]=sellCurSLStreak[h];
         }
         else if(pnl>=0.0) sellCurSLStreak[h]=0;
      }
   }
   if(InpPrintAnalyzer)
   {
      Print("=========== V6.0 SMALL CANDLE FLOW HOUR ANALYZER ===========");
      for(int h=0;h<24;h++)
      {
         if(buyT[h]==0 && sellT[h]==0) continue;
         double bwr=buyT[h]>0 ? 100.0*buyW[h]/buyT[h] : 0.0;
         double swr=sellT[h]>0 ? 100.0*sellW[h]/sellT[h] : 0.0;
         PrintFormat("H%02d | BUY T=%d WR=%.1f%% PnL=%.2f | SELL T=%d WR=%.1f%% PnL=%.2f",
                     h,buyT[h],bwr,buyP[h],sellT[h],swr,sellP[h]);
      }
      Print("============================================================");
   }
   if(InpPrintSLHourAnalyzer)
   {
      Print("=========== V6.0 SL-HOUR ANALYZER ===========================");
      for(int h=0;h<24;h++)
      {
         if(buyT[h]>0)
            PrintFormat("H%02d | BUY  | T=%d TP=%d SL=%d PnL=%.2f",
                        h,buyT[h],buyTP[h],buySL[h],buyP[h]);
         if(sellT[h]>0)
            PrintFormat("H%02d | SELL | T=%d TP=%d SL=%d PnL=%.2f",
                        h,sellT[h],sellTP[h],sellSL[h],sellP[h]);
      }
      Print("============================================================");
   }
   PrintV48MarketConditionAnalyzer();
   return 0.0;
}
//+------------------------------------------------------------------+
