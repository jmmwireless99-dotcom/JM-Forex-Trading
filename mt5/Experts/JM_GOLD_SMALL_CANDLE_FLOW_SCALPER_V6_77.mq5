//+------------------------------------------------------------------+
//| JM_GOLD_SMALL_CANDLE_FLOW_SCALPER_V6_77.mq5                      |
//| V6.77 BEST MASTER — SL $15 @ 0.01, no stall/MFE lock (best net in tests) |
//+------------------------------------------------------------------+
#define JMG_SCALPER_VERSION "6.77"
#property version   "6.77"
#property copyright "JM Tech Solution"
#property description "GOLD# V6.77: adjustable InpLots + safe USD SL/TP"

#include <Trade/Trade.mqh>
CTrade trade;

string JmgOrderComment()
{
   return StringFormat("JM GOLD SCALPER VERSION %s",JMG_SCALPER_VERSION);
}

bool V48EntryMetrics(const datetime entryTime,
                     double &adx,double &m5atr,double &gapATR,double &slopeATR,
                     double &m1atr,double &rsi,double &body,double &rangeATR);

input string InpSymbol              = "GOLD#";
input double InpLots                = 0.01;
input long   InpMagic               = 26091077;
input string InpMasterBuildTag      = "V6.77-BEST-MASTER-SL15";
input int    InpBrokerUtcOffsetHours = 3;

input int    InpM5FastEMA           = 20;
input int    InpM5SlowEMA           = 50;
input int    InpM5ADXPeriod         = 14;
input double InpMinADX              = 16.0;
input bool   InpBlockMidADX          = true;
input double InpBlockADXFrom         = 25.0;
input double InpBlockADXTo           = 35.0;
input bool   InpBlockBuyWeakEmaGap   = true;
input double InpBuyWeakGapATR        = 0.25;
input int    InpM1FastEMA           = 9;
input int    InpM1SlowEMA           = 21;
input int    InpM1RSIPeriod         = 14;

input int    InpM1ATRPeriod         = 14;
input double InpSmallBodyRatioMax   = 0.45;
input double InpBreakBufferATR      = 0.05;
input bool   InpRequireM1Flow       = true;
input bool   InpUseChopFilter        = true;
input double InpMinM5GapATR        = 0.06;
input double InpWeakADXLevel       = 20.0;
input double InpMinSmallRangeATR   = 0.15;
input double InpMaxSmallRangeATR   = 0.80;
input bool   InpUseFlowScore       = true;
input int    InpMinFlowScore       = 3;
input bool   InpUseDynamicHourScore  = false;
input int    InpStrongHourScoreAdj  = -1;
input int    InpWeakHourScoreAdj    = 1;
input bool   InpUseDirectionalRouter = false;
input int    InpOppositeDirPenalty  = 1;
input int    InpDefensivePenalty    = 2;
input int    InpPreferredBonus      = -1;
input bool   InpUseProfitZoneRouter  = false;
input int    InpProfitZoneBonus     = -1;
input int    InpLossZonePenalty     = 2;

input double InpBuyRSIMin           = 46.0;
input double InpBuyRSIMax           = 68.0;
input double InpSellRSIMin          = 32.0;
input double InpSellRSIMax          = 54.0;

input bool   InpUseFixedSLUsd        = true;
input double InpFixedSLUsd           = 15.0;
input double InpReferenceLot         = 0.01;
input bool   InpScaleUsdTargetsWithLot = true;
input bool   InpUseDynamicTP           = true;
input double InpTP_BaseUsd             = 30.0;
input double InpTP_Tier2Usd            = 40.0;
input double InpTP_Tier3Usd            = 50.0;
input double InpTP_Tier4Usd            = 60.0;
input double InpTP_Tier5Usd            = 75.0;
input double InpDynADX40               = 32.0;
input double InpDynATR40               = 8.0;
input double InpDynADX50               = 35.0;
input double InpDynATR50               = 10.0;
input double InpDynADX60               = 38.0;
input double InpDynATR60               = 12.0;
input double InpDynADX75               = 42.0;
input double InpDynATR75               = 14.0;
input double InpDynGap40               = 0.55;
input double InpDynGap50               = 0.75;
input double InpDynGap60               = 0.95;
input double InpDynGap75               = 1.15;
input int    InpTpOpportunityLookaheadMin = 60;
input int    InpSRLookbackM15Bars         = 48;

input int    InpMinSecondsBetween   = 20;
input int    InpMaxSpreadPoints     = 0;
input bool   InpAllowBuy            = true;
input bool   InpAllowSell           = true;
input bool   InpBest4HoursOnly       = true;
input bool   InpShowPanel           = false;
input bool   InpShowLotOnChart      = true;
input bool   InpPrintAllAnalyzers        = true;
input bool   InpPrintAnalyzer       = true;
input bool   InpPrintSLHourAnalyzer  = true;
input bool   InpPrintMarketConditionAnalyzer = true;
input bool   InpPrintDetailedEntryAnalyzer = true;
input bool   InpPrintLossCauseAnalyzer   = true;
input bool   InpPrintLossRootCauseAnalyzer = true;
input bool   InpPrintTpOpportunityAnalyzer = true;
input bool   InpUseStrictProfitHours = false;
input bool   InpUseProfitHourRouter = false;
input bool   InpUseV38Refinement      = false;
input bool   InpUseSafeSessionAB       = false;
input bool   InpBlockH17BuyOnly        = false;
input bool   InpBlockH16H17All       = false;
input int    InpABAsiaStartHour      = 0;
input int    InpABAsiaEndHour        = 7;
input int    InpABEuropeStartHour    = 7;
input int    InpABEuropeEndHour      = 15;
input int    InpABUSStartHour        = 15;
input int    InpABUSEndHour          = 24;

input bool   InpUseV640ProfitHourRouter = true;
input bool   InpAllHoursResearchMode     = false;
input int    InpResearchStartHour        = 0;
input int    InpResearchEndHour          = 24;
input bool   InpPrint24HEntryProblemAnalyzer = true;
input bool   InpPrintEachLossDetail      = false;

input bool   InpV641BlockSellADX20To25 = true;
input double InpV641SellADXBlockFrom   = 20.0;
input double InpV641SellADXBlockTo     = 25.0;
input bool   InpV642BlockBuyGap050To100 = true;
input double InpV642BuyGapBlockFrom     = 0.50;
input double InpV642BuyGapBlockTo       = 1.00;
input bool   InpV643BlockSellGap075To100 = true;
input double InpV643SellGapBlockFrom     = 0.75;
input double InpV643SellGapBlockTo       = 1.00;
input bool   InpConvertTP60Class        = true;
input double InpTP60OverrideUsd         = 45.0;
input bool   InpPrintTP60Conversion     = false;

string g_symbol;
int hM5Fast=INVALID_HANDLE, hM5Slow=INVALID_HANDLE, hM5ADX=INVALID_HANDLE, hM5ATR=INVALID_HANDLE;
int hM1Fast=INVALID_HANDLE, hM1Slow=INVALID_HANDLE, hM1RSI=INVALID_HANDLE, hM1ATR=INVALID_HANDLE;
datetime g_lastEntryTime=0;
datetime g_lastSignalBar=0;
string g_status="Starting";

#define JMG_DASH_PREFIX "JMG77_"

bool V640ProfitHourAllowed(const int dir,const int hour);
string V640HourDisplay(const int serverHour);
string BiasVsHourLine(const int bias,const int serverHour);
string BiasWord(const int bias);

int PhtHour(const int serverHour)
{
   int add=8-InpBrokerUtcOffsetHours;
   return (serverHour+add+24)%24;
}

string PhtLabel(const int serverHour)
{
   return StringFormat("H%02d server = %02d:00 PHT",serverHour,PhtHour(serverHour));
}

ENUM_ORDER_TYPE_FILLING DetectFilling()
{
   const int filling=(int)SymbolInfoInteger(g_symbol,SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   if((filling & SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
}

bool HasOpenPosition()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL)==g_symbol &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic)
         return true;
   }
   return false;
}

bool SpreadOK()
{
   if(InpMaxSpreadPoints<=0) return true;
   MqlTick q; if(!SymbolInfoTick(g_symbol,q)) return false;
   double point=SymbolInfoDouble(g_symbol,SYMBOL_POINT);
   if(point<=0.0) return false;
   return ((q.ask-q.bid)/point <= InpMaxSpreadPoints);
}

double MoneyToPriceDistance(double money,double lots)
{
   double ts=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_SIZE);
   double tv=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_VALUE);
   if(money<=0 || lots<=0 || ts<=0 || tv<=0) return 0.0;
   return (money*ts)/(tv*lots);
}

double NormalizeVolume(double lots)
{
   double vmin=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_STEP);
   if(step<=0.0) step=0.01;
   if(lots<vmin) lots=vmin;
   if(lots>vmax) lots=vmax;
   return MathFloor(lots/step+0.0000001)*step;
}

double LotUsdScale(const double lots)
{
   if(!InpScaleUsdTargetsWithLot) return 1.0;
   if(InpReferenceLot<=0.0) return 1.0;
   return lots/InpReferenceLot;
}

double EffectiveSlUsd(const double lots)
{
   if(!InpUseFixedSLUsd || InpFixedSLUsd<=0.0) return 0.0;
   return InpFixedSLUsd*LotUsdScale(lots);
}

double EffectiveTpUsd(const double baseTpUsd,const double lots)
{
   return baseTpUsd*LotUsdScale(lots);
}

double UsdFromPriceDistance(const double priceDist,const double lots)
{
   double ts=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_SIZE);
   double tv=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_VALUE);
   if(priceDist<=0.0 || lots<=0.0 || ts<=0.0 || tv<=0.0) return 0.0;
   return (priceDist/ts)*tv*lots;
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
   return (rangeAtr>=InpMinSmallRangeATR && rangeAtr<=InpMaxSmallRangeATR &&
           bodyRatio<=InpSmallBodyRatioMax);
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

string BiasWord(const int bias)
{
   if(bias>0) return "BUY";
   if(bias<0) return "SELL";
   return "NONE";
}

string TrendLabel(const int bias)
{
   if(bias>0) return "BULL (M5 EMA up)";
   if(bias<0) return "BEAR (M5 EMA down)";
   return "FLAT / weak ADX";
}

string FlowLabel(const int flow)
{
   if(flow>0) return "M1 UP";
   if(flow<0) return "M1 DOWN";
   return "M1 flat";
}

string ScoreMark(const bool ok)
{
   return ok ? "[+]" : "[-]";
}

void DashboardDeleteObjects()
{
   const int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string name=ObjectName(0,i,0,-1);
      if(StringFind(name,JMG_DASH_PREFIX)==0)
         ObjectDelete(0,name);
   }
}

void UpdateChartLotDisplay()
{
   const string name=JMG_DASH_PREFIX"LotBadge";
   if(MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION))
      return;

   if(!InpShowLotOnChart)
   {
      if(ObjectFind(0,name)>=0)
      {
         ObjectDelete(0,name);
         ChartRedraw(0);
      }
      return;
   }

   const double lots=NormalizeVolume(InpLots);
   const double slUsd=EffectiveSlUsd(lots);
   const string text=StringFormat("VERSION %s  |  LOT: %.2f  |  SL~$%.0f",
                                  JMG_SCALPER_VERSION,lots,slUsd);

   if(ObjectFind(0,name)<0)
   {
      if(!ObjectCreate(0,name,OBJ_LABEL,0,0,0)) return;
      ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
      ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_RIGHT_UPPER);
      ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
      ObjectSetInteger(0,name,OBJPROP_FONTSIZE,11);
      ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   }
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,14);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,22);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrGold);
   ChartRedraw(0);
}

bool DashboardLabel(const string id,const int x,const int y,const string text,
                    const color clr,const int fontSize=9)
{
   const string name=JMG_DASH_PREFIX+id;
   if(ObjectFind(0,name)<0)
   {
      if(!ObjectCreate(0,name,OBJ_LABEL,0,0,0)) return false;
      ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
      ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
      ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
      ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   }
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,fontSize);
   return true;
}

bool DashboardBackground(const int width,const int height)
{
   const string name=JMG_DASH_PREFIX"BG";
   if(ObjectFind(0,name)<0)
   {
      if(!ObjectCreate(0,name,OBJ_RECTANGLE_LABEL,0,0,0)) return false;
      ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
      ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
      ObjectSetInteger(0,name,OBJPROP_BACK,false);
   }
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,8);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,18);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,width);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,height);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,clrBlack);
   ObjectSetInteger(0,name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrDimGray);
   return true;
}

string PositionDashboardLine()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong t=PositionGetTicket(i);
      if(t==0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=g_symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      long type=PositionGetInteger(POSITION_TYPE);
      double vol=PositionGetDouble(POSITION_VOLUME);
      double pl=PositionGetDouble(POSITION_PROFIT);
      string side=(type==POSITION_TYPE_BUY ? "BUY" : "SELL");
      return StringFormat("Position: %s | Lot %.2f | Float $%.2f",side,vol,pl);
   }
   return "Position: FLAT (waiting entry)";
}

enum HourRoute { ROUTE_BOTH=0, ROUTE_BUY=1, ROUTE_SELL=2, ROUTE_DEFENSIVE=3 };

HourRoute GetHourRoute(const int hour)
{
   if(hour==1 || hour==2 || hour==12) return ROUTE_BOTH;
   if(hour==5 || hour==8 || hour==10 || hour==13 ||
      hour==16 || hour==17 || hour==20 || hour==21) return ROUTE_SELL;
   if(hour==7 || hour==23) return ROUTE_BUY;
   if(hour==3 || hour==4 || hour==6 || hour==9 || hour==11 ||
      hour==14 || hour==15 || hour==18 || hour==19 || hour==22)
      return ROUTE_DEFENSIVE;
   return ROUTE_BOTH;
}

int ProfitZoneAdjustment(const int dir,const int hour)
{
   if(!InpUseProfitZoneRouter) return 0;
   if(dir>0)
   {
      if(hour==4 || hour==7 || hour==23) return InpProfitZoneBonus;
      if(hour==5 || hour==6 || hour==10 || hour==12 ||
         hour==13 || hour==15 || hour==19 || hour==20) return InpLossZonePenalty;
   }
   else
   {
      if(hour==1 || hour==2 || hour==5 || hour==8 ||
         hour==12 || hour==13 || hour==16 || hour==17 ||
         hour==20 || hour==21) return InpProfitZoneBonus;
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
         if(hour==7 || hour==23) need += InpStrongHourScoreAdj;
         if(hour==5 || hour==13 || hour==19 || hour==20) need += InpWeakHourScoreAdj;
      }
      else
      {
         if(hour==5 || hour==8 || hour==10 || hour==13 ||
            hour==16 || hour==17 || hour==20 || hour==21) need += InpStrongHourScoreAdj;
         if(hour==11 || hour==18 || hour==19 || hour==22) need += InpWeakHourScoreAdj;
      }
   }
   if(InpUseDirectionalRouter)
   {
      HourRoute route=GetHourRoute(hour);
      if(route==ROUTE_DEFENSIVE) need += InpDefensivePenalty;
      else if(route==ROUTE_BUY) need += (dir>0 ? InpPreferredBonus : InpOppositeDirPenalty);
      else if(route==ROUTE_SELL) need += (dir<0 ? InpPreferredBonus : InpOppositeDirPenalty);
   }
   need += ProfitZoneAdjustment(dir,hour);
   if(need<1) need=1;
   if(need>6) need=6;
   return need;
}

double V634SelectTPUsd()
{
   if(!InpUseDynamicTP) return InpTP_BaseUsd;

   double adx=0.0,m5atr=0.0,gap=0.0,slope=0.0,m1atr=0.0,rsi=0.0,body=0.0,rangeATR=0.0;
   if(!V48EntryMetrics(TimeCurrent(),adx,m5atr,gap,slope,m1atr,rsi,body,rangeATR))
      return InpTP_BaseUsd;

   double tp=InpTP_BaseUsd;
   if(adx>=InpDynADX40 && m5atr>=InpDynATR40 && gap>=InpDynGap40) tp=InpTP_Tier2Usd;
   if(adx>=InpDynADX50 && m5atr>=InpDynATR50 && gap>=InpDynGap50) tp=InpTP_Tier3Usd;
   if(adx>=InpDynADX60 && m5atr>=InpDynATR60 && gap>=InpDynGap60) tp=InpTP_Tier4Usd;
   if(adx>=InpDynADX75 && m5atr>=InpDynATR75 && gap>=InpDynGap75) tp=InpTP_Tier5Usd;
   return tp;
}

void UpdateDashboard()
{
   if(!InpShowPanel) return;
   if(MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION)) return;

   MqlDateTime tmNow;
   TimeToStruct(TimeCurrent(),tmNow);

   const double lots=NormalizeVolume(InpLots);
   double slUsd=EffectiveSlUsd(lots);
   double tpBase=V634SelectTPUsd();
   if(InpConvertTP60Class && MathAbs(tpBase-InpTP_Tier4Usd)<0.01)
      tpBase=InpTP60OverrideUsd;
   double tpUsd=EffectiveTpUsd(tpBase,lots);

   double adx=0.0,gapATR=0.0;
   int bias=M5Bias(adx,gapATR);

   double rsi=0.0;
   int flow=M1Flow(rsi);

   MqlRates small;
   double atr=0.0,bodyRatio=0.0,rangeAtr=0.0;
   bool smallOk=GetSmallCandle(small,atr,bodyRatio,rangeAtr);

   int flowScore=0;
   int requiredScore=InpMinFlowScore;
   if(bias!=0)
   {
      flowScore=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
      requiredScore=DynamicRequiredScore(bias,tmNow.hour);
   }

   MqlTick q;
   bool tickOk=SymbolInfoTick(g_symbol,q);
   double buffer=(atr>0.0 ? atr*InpBreakBufferATR : 0.0);
   bool buyBreak=tickOk && smallOk && (q.ask > small.high + buffer);
   bool sellBreak=tickOk && smallOk && (q.bid < small.low - buffer);

   bool rsiBuyOk=(rsi>=InpBuyRSIMin && rsi<=InpBuyRSIMax);
   bool rsiSellOk=(rsi>=InpSellRSIMin && rsi<=InpSellRSIMax);

   string hourWhy="";
   bool hourOk=(bias!=0 && HourDirectionAllowed(bias,tmNow.hour,hourWhy));

   color trendClr=clrSilver;
   if(bias>0) trendClr=clrLime;
   else if(bias<0) trendClr=clrOrangeRed;

   double emaFast=0.0,emaSlow=0.0;
   Read1(hM5Fast,1,emaFast);
   Read1(hM5Slow,1,emaSlow);
   const int phtHr=PhtHour(tmNow.hour);

   const int x0=16;
   int y=26;
   const int dy=14;

   DashboardBackground(440,400);

   DashboardLabel("T0",x0,y,StringFormat("JM GOLD SCALPER V%s | %s",JMG_SCALPER_VERSION,g_symbol),clrGold,10);
   y+=dy+2;
   DashboardLabel("T1",x0,y,StringFormat("LOT %.2f (ref %.2f) | SL~$%.2f | TP~$%.2f | scale %s",
                  lots,InpReferenceLot,slUsd,tpUsd,InpScaleUsdTargetsWithLot?"AUTO":"FIXED"),clrWhite);
   y+=dy;
   DashboardLabel("T2",x0,y,StringFormat("Clock: server %02d:%02d (UTC+%d) | PHT %02d:%02d",
                  tmNow.hour,tmNow.min,InpBrokerUtcOffsetHours,phtHr,tmNow.min),clrLightGray);
   y+=dy;
   DashboardLabel("T2b",x0,y,V640HourDisplay(tmNow.hour),
                  InpUseV640ProfitHourRouter?clrAqua:clrGray);
   y+=dy;
   const bool biasHourOn=(bias!=0 && V640ProfitHourAllowed(bias,tmNow.hour));
   DashboardLabel("T2c",x0,y,BiasVsHourLine(bias,tmNow.hour),
                  bias==0?clrGray:(biasHourOn || !InpUseV640ProfitHourRouter)?clrLime:clrOrangeRed);
   y+=dy+2;
   DashboardLabel("T3",x0,y,"TREND: "+TrendLabel(bias)+" | BIAS "+BiasWord(bias),trendClr,10);
   y+=dy;
   DashboardLabel("T3b",x0,y,StringFormat("M5 EMA%d=%.2f EMA%d=%.2f | chop ADX>=%.0f gap>=%.2f",
                  InpM5FastEMA,emaFast,InpM5SlowEMA,emaSlow,InpMinADX,InpMinM5GapATR),clrDarkGray,8);
   y+=dy;
   DashboardLabel("T4",x0,y,StringFormat("M5 ADX=%.1f | GapATR=%.3f | %s%s M5",
                  adx,gapATR,FlowLabel(flow),
                  (InpRequireM1Flow && bias!=0 && flow!=bias ? " (DISAGREE)" : "")),
                  (InpRequireM1Flow && bias!=0 && flow!=bias ? clrOrangeRed : clrWhite));
   y+=dy;
   DashboardLabel("T5",x0,y,StringFormat("M1 RSI=%.1f | ATR=%.2f | Entry RSI buy %.0f-%.0f sell %.0f-%.0f",
                  rsi,atr,InpBuyRSIMin,InpBuyRSIMax,InpSellRSIMin,InpSellRSIMax),clrWhite);
   y+=dy+2;

   string smallTxt=smallOk
      ? StringFormat("Small candle: YES | body=%.0f%% rangeATR=%.2f",
                     bodyRatio*100.0,rangeAtr)
      : "Small candle: NO (waiting compression bar)";
   DashboardLabel("T6",x0,y,smallTxt,smallOk?clrAqua:clrGray);
   y+=dy;
   DashboardLabel("T7",x0,y,StringFormat("Breakout: BUY %s | SELL %s | buffer ATR×%.2f",
                  buyBreak?"READY":"---",sellBreak?"READY":"---",InpBreakBufferATR),
                  clrWhite);
   y+=dy;
   DashboardLabel("T8",x0,y,StringFormat("RSI gate: BUY %s | SELL %s",
                  rsiBuyOk?"OK":"block",rsiSellOk?"OK":"block"),
                  clrLightGray);
   y+=dy+2;

   if(bias!=0)
   {
      DashboardLabel("T9",x0,y,StringFormat("Score %d / need %d | Hour %s",
                     flowScore,requiredScore,hourOk?"ALLOW":"BLOCK"),hourOk?clrLime:clrOrangeRed);
      y+=dy;
      DashboardLabel("T10a",x0,y,
         StringFormat("%s M1=M5  %s ADX  %s Gap  %s RngATR",
            ScoreMark(flow==bias),ScoreMark(adx>=InpWeakADXLevel),
            ScoreMark(gapATR>=InpMinM5GapATR),
            ScoreMark(rangeAtr>=0.25 && rangeAtr<=0.65)),clrDarkGray,8);
      y+=dy;
      bool rsiScore=(bias>0 ? (rsi>=48.0 && rsi<=64.0) : (rsi>=36.0 && rsi<=52.0));
      DashboardLabel("T10b",x0,y,
         StringFormat("%s RSI zone  %s body ratio",
            ScoreMark(rsiScore),
            ScoreMark(bodyRatio>=0.12 && bodyRatio<=0.40)),clrDarkGray,8);
      y+=dy;
   }

   DashboardLabel("T11",x0,y,PositionDashboardLine(),clrYellow);
   y+=dy;
   DashboardLabel("T12",x0,y,"Status: "+g_status,clrWhite);
   if(!hourOk && hourWhy!="")
   {
      y+=dy;
      DashboardLabel("T13",x0,y,hourWhy,clrOrangeRed,8);
   }

   ChartRedraw(0);
}

bool HourDirectionAllowed(const int dir,const int hour,string &why);

bool OpenTrade(int dir,double atr,int score,const string reason)
{
   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return false;

   const double lots=NormalizeVolume(InpLots);
   if(lots<=0.0) return false;

   double target=V634SelectTPUsd();
   if(InpConvertTP60Class && MathAbs(target-InpTP_Tier4Usd)<0.01)
   {
      double original=target;
      target=InpTP60OverrideUsd;
      g_status=StringFormat("TP60 class $%.0f -> $%.0f",original,target);
      if(InpPrintTP60Conversion)
         PrintFormat("TP60 CONVERT | %s | $%.0f -> $%.0f",
                     dir>0?"BUY":"SELL",original,target);
   }

   target=EffectiveTpUsd(target,lots);
   double risk=(InpUseFixedSLUsd && InpFixedSLUsd>0.0)
               ? EffectiveSlUsd(lots)
               : target/1.35;

   double tpDist=MoneyToPriceDistance(target,lots);
   double slDist=MoneyToPriceDistance(risk,lots);
   if(tpDist<=0 || slDist<=0)
   {
      g_status="USD->price distance failed (tick size/value)";
      Print(g_status);
      return false;
   }

   const double slDistRaw=slDist;
   tpDist=RespectStops(tpDist);
   slDist=RespectStops(slDist);
   if(slDist>slDistRaw*1.05)
   {
      double est=UsdFromPriceDistance(slDist,lots);
      PrintFormat("WARN: broker min stop widened SL | wanted ~$%.2f | est ~$%.2f at lot %.2f",
                  risk,est,lots);
   }
   int dg=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFilling(DetectFilling());

   bool ok=false;
   if(dir>0)
   {
      double sl=NormalizeDouble(q.ask-slDist,dg);
      double tp=NormalizeDouble(q.ask+tpDist,dg);
      ok=trade.Buy(lots,g_symbol,0.0,sl,tp,JmgOrderComment());
   }
   else
   {
      double sl=NormalizeDouble(q.bid+slDist,dg);
      double tp=NormalizeDouble(q.bid-tpDist,dg);
      ok=trade.Sell(lots,g_symbol,0.0,sl,tp,JmgOrderComment());
   }

   if(ok)
   {
      g_lastEntryTime=TimeCurrent();
      g_status=StringFormat("%s OPEN | Lot=%.2f TP~$%.2f SL~$%.2f",
                            dir>0?"BUY":"SELL",lots,target,risk);
      Print(g_status," | ",reason," | MT5 comment: ",JmgOrderComment());
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
      hM5ATR==INVALID_HANDLE || hM1Fast==INVALID_HANDLE || hM1Slow==INVALID_HANDLE ||
      hM1RSI==INVALID_HANDLE || hM1ATR==INVALID_HANDLE)
      return INIT_FAILED;

   trade.SetExpertMagicNumber(InpMagic);
   Print("==============================================================");
   Print("JM GOLD V6.77 | V6.55 BASE | ",InpMasterBuildTag);
   const double lots=NormalizeVolume(InpLots);
   PrintFormat("Lot=%.2f | SL~$%.2f TP scales same ratio | ref %.2f lot = $%.0f SL | auto=%s",
               lots,EffectiveSlUsd(lots),InpReferenceLot,InpFixedSLUsd,
               InpScaleUsdTargetsWithLot?"ON":"OFF");
   Print("V640-V643 | TP60->45 | score 3 | palitan InpLots lang — SL/TP USD sumusunod");
   PrintFormat("Broker UTC+%d | PHT = server + %d",InpBrokerUtcOffsetHours,8-InpBrokerUtcOffsetHours);
   if(InpUseV640ProfitHourRouter)
   {
      Print("V640 hours ON (PHT):");
      Print("  SELL  09:00, 10:00, 13:00, 16:00, 17:00, 02:00");
      Print("  BUY   10:00, 13:00, 22:00, 00:00, 03:00");
   }
   else if(InpBest4HoursOnly)
      Print("Hybrid 4h ON | PHT SELL 10/13/02 | BUY 10/13/04");
   Print("==============================================================");
   if(!MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION))
      UpdateChartLotDisplay();
   if(InpShowPanel && !MQLInfoInteger(MQL_TESTER))
      UpdateDashboard();
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
   DashboardDeleteObjects();
   Comment("");
}

bool StrictProfitHourAllowed(const int dir,const int hour)
{
   if(!InpUseStrictProfitHours) return true;
   if(dir<0)
      return (hour==1 || hour==2 || hour==5 || hour==8 ||
              hour==12 || hour==16 || hour==17 || hour==20 || hour==21);
   if(dir>0) return (hour==23);
   return false;
}

bool ProfitHourAllowed(const int dir,const int hour)
{
   if(!InpUseProfitHourRouter) return true;
   if(dir>0)
   {
      if(hour==5 || hour==6 || hour==10 || hour==12 ||
         hour==13 || hour==14 || hour==15 || hour==19 || hour==20) return false;
      if(InpUseV38Refinement &&
         (hour==4 || hour==11 || hour==16 || hour==18 || hour==22)) return false;
      return true;
   }
   if(dir<0)
   {
      if(hour==3 || hour==6 || hour==9 || hour==11 ||
         hour==15 || hour==18 || hour==19 || hour==22 || hour==23) return false;
      if(InpUseV38Refinement &&
         (hour==7 || hour==10 || hour==13 || hour==14)) return false;
      return true;
   }
   return false;
}

enum ABSess { AB_ASIA=0, AB_EUROPE=1, AB_US=2 };

ABSess ABSessionByHour(const int hour)
{
   if(hour>=InpABAsiaStartHour && hour<InpABAsiaEndHour) return AB_ASIA;
   if(hour>=InpABEuropeStartHour && hour<InpABEuropeEndHour) return AB_EUROPE;
   return AB_US;
}

bool SafeABDirectionAllowed(const int dir,const int hour)
{
   if(!InpUseSafeSessionAB) return true;
   ABSess s=ABSessionByHour(hour);
   if(s==AB_ASIA || s==AB_EUROPE) return (dir<0);
   return true;
}

bool V640ProfitHourAllowed(const int dir,const int hour)
{
   if(!InpUseV640ProfitHourRouter) return true;
   if(hour==4  && dir<0) return true;
   if(hour==5)           return true;
   if(hour==8)           return true;
   if(hour==11 && dir<0) return true;
   if(hour==12 && dir<0) return true;
   if(hour==17 && dir>0) return true;
   if(hour==19 && dir>0) return true;
   if(hour==21 && dir<0) return true;
   if(hour==22 && dir>0) return true;
   return false;
}

string V640HourDisplay(const int serverHour)
{
   const int pht=PhtHour(serverHour);
   if(!InpUseV640ProfitHourRouter)
      return StringFormat("V640 router OFF | PHT %02d:00 — BUY+SELL allowed",pht);
   const bool buyOn=V640ProfitHourAllowed(1,serverHour);
   const bool sellOn=V640ProfitHourAllowed(-1,serverHour);
   string slot;
   if(buyOn && sellOn) slot="BUY ON | SELL ON";
   else if(buyOn) slot="BUY ON | SELL OFF";
   else if(sellOn) slot="BUY OFF | SELL ON";
   else slot="BUY OFF | SELL OFF";
   return StringFormat("V640 @ PHT %02d:00 | %s",pht,slot);
}

string BiasVsHourLine(const int bias,const int serverHour)
{
   if(bias==0)
      return "M5 BIAS: NONE — need ADX/EMA trend";
   if(!InpUseV640ProfitHourRouter)
      return StringFormat("M5 BIAS: %s | hour gate OFF",BiasWord(bias));
   const bool ok=V640ProfitHourAllowed(bias,serverHour);
   return StringFormat("M5 BIAS: %s | oras na ito para sa bias: %s",
                       BiasWord(bias),ok?"ON (pwede)":"OFF (blocked)");
}

bool HybridHourDirectionAllowed(const int dir,const int hour)
{
   if(!InpBest4HoursOnly) return true;
   if(hour==5 || hour==8) return true;
   if(hour==21 && dir<0) return true;
   if(hour==23 && dir>0) return true;
   return false;
}

bool HourDirectionAllowed(const int dir,const int hour,string &why)
{
   if(InpUseV640ProfitHourRouter)
   {
      if(!V640ProfitHourAllowed(dir,hour))
      {
         why=StringFormat("V640 OFF | %s %s",PhtLabel(hour),dir>0?"BUY":"SELL");
         return false;
      }
      return true;
   }
   if(InpAllHoursResearchMode)
   {
      if(hour<InpResearchStartHour || hour>=InpResearchEndHour)
      {
         why=StringFormat("24H research OFF | H%02d",hour);
         return false;
      }
      return true;
   }
   if(!HybridHourDirectionAllowed(dir,hour))
   {
      why=StringFormat("Hybrid 4h OFF | %s %s",PhtLabel(hour),dir>0?"BUY":"SELL");
      return false;
   }
   return true;
}

void OnTick()
{
   if(!MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION))
   {
      static datetime s_lastUiBar=0;
      datetime bar0=iTime(g_symbol,PERIOD_M1,0);
      if(bar0!=0 && bar0!=s_lastUiBar)
      {
         s_lastUiBar=bar0;
         UpdateChartLotDisplay();
         if(InpShowPanel)
            UpdateDashboard();
      }
   }
   if(HasOpenPosition()) return;
   if(!SpreadOK())
   {
      g_status="Spread too wide";
      return;
   }
   if((TimeCurrent()-g_lastEntryTime)<InpMinSecondsBetween) return;

   MqlRates small;
   double atr,bodyRatio,rangeAtr;
   if(!GetSmallCandle(small,atr,bodyRatio,rangeAtr))
   {
      g_status="Waiting for M1 small candle";
      return;
   }
   if(small.time==g_lastSignalBar) return;

   double adx=0.0,rsi=0.0,gapATR=0.0;
   int bias=M5Bias(adx,gapATR);
   if(bias==0)
   {
      g_status="No M5 flow / ADX weak";
      return;
   }

   if(InpBlockMidADX && adx>=InpBlockADXFrom && adx<InpBlockADXTo)
   {
      g_status=StringFormat("MID ADX BLOCK | ADX=%.1f",adx);
      return;
   }
   if(InpV641BlockSellADX20To25 && bias<0 &&
      adx>=InpV641SellADXBlockFrom && adx<InpV641SellADXBlockTo)
   {
      g_status=StringFormat("SELL ADX20-25 BLOCK | ADX=%.1f",adx);
      return;
   }
   if(InpV642BlockBuyGap050To100 && bias>0 &&
      gapATR>=InpV642BuyGapBlockFrom && gapATR<InpV642BuyGapBlockTo)
   {
      g_status=StringFormat("BUY GAP0.50-1.00 BLOCK | GapATR=%.3f",gapATR);
      return;
   }
   if(InpV643BlockSellGap075To100 && bias<0 &&
      gapATR>=InpV643SellGapBlockFrom && gapATR<InpV643SellGapBlockTo)
   {
      g_status=StringFormat("SELL GAP0.75-1.00 BLOCK | GapATR=%.3f",gapATR);
      return;
   }
   if(InpBlockBuyWeakEmaGap && bias>0 && gapATR<InpBuyWeakGapATR)
   {
      g_status=StringFormat("BUY WEAK EMA GAP BLOCK | GapATR=%.3f",gapATR);
      return;
   }

   int flow=M1Flow(rsi);
   if(InpRequireM1Flow && flow!=bias)
   {
      g_status="M1 flow disagrees with M5";
      return;
   }

   int flowScore=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
   MqlDateTime tmNow;
   TimeToStruct(TimeCurrent(),tmNow);

   string hourWhy="";
   if(!HourDirectionAllowed(bias,tmNow.hour,hourWhy))
   {
      g_status=hourWhy;
      return;
   }
   if(InpBlockH16H17All && (tmNow.hour==16 || tmNow.hour==17))
   {
      g_status=StringFormat("HARD BLOCK H%02d ALL / %02d PHT",tmNow.hour,PhtHour(tmNow.hour));
      return;
   }
   if(!StrictProfitHourAllowed(bias,tmNow.hour))
   {
      g_status=StringFormat("strict-hour reject %s %s",PhtLabel(tmNow.hour),bias>0?"BUY":"SELL");
      return;
   }

   int requiredScore=DynamicRequiredScore(bias,tmNow.hour);
   if(InpUseFlowScore && flowScore<requiredScore)
   {
      g_status=StringFormat("Flow score %d < dynamic %d",flowScore,requiredScore);
      return;
   }
   if(!ProfitHourAllowed(bias,tmNow.hour))
   {
      g_status=StringFormat("Hour router reject %s %s",PhtLabel(tmNow.hour),bias>0?"BUY":"SELL");
      return;
   }
   if(!SafeABDirectionAllowed(bias,tmNow.hour))
   {
      g_status=StringFormat("SAFE-AB reject %s %s",PhtLabel(tmNow.hour),bias>0?"BUY":"SELL");
      return;
   }
   if(InpBlockH17BuyOnly && bias>0 && tmNow.hour==17)
   {
      g_status="reject H17 BUY / 22:00 PHT";
      return;
   }

   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return;
   double buffer=atr*InpBreakBufferATR;
   bool buyBreak=(q.ask > small.high + buffer);
   bool sellBreak=(q.bid < small.low  - buffer);

   if(bias>0 && InpAllowBuy && buyBreak && rsi>=InpBuyRSIMin && rsi<=InpBuyRSIMax)
   {
      if(OpenTrade(1,atr,flowScore,StringFormat("SMALL_FLOW BUY | Score=%d Need=%d ADX=%.1f GapATR=%.3f RSI=%.1f PHT=%02d",
                                   flowScore,requiredScore,adx,gapATR,rsi,PhtHour(tmNow.hour))))
         g_lastSignalBar=small.time;
      return;
   }
   if(bias<0 && InpAllowSell && sellBreak && rsi>=InpSellRSIMin && rsi<=InpSellRSIMax)
   {
      if(OpenTrade(-1,atr,flowScore,StringFormat("SMALL_FLOW SELL | Score=%d Need=%d ADX=%.1f GapATR=%.3f RSI=%.1f PHT=%02d",
                                    flowScore,requiredScore,adx,gapATR,rsi,PhtHour(tmNow.hour))))
         g_lastSignalBar=small.time;
      return;
   }
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

string V618Condition(double adx,double gap,double rsi,double body)
{
   if(adx<InpMinADX) return "LOW_ADX";
   if(gap<InpMinM5GapATR) return "WEAK_EMA_GAP";
   if(rsi>=70.0 || rsi<=30.0) return "RSI_EXTREME";
   if(body<=0.15) return "MICRO_BODY";
   if(body>=0.85) return "LARGE_BODY";
   if(adx>=30.0 && gap>=0.25) return "STRONG_TREND";
   return "NORMAL";
}

#include "JM_GOLD_V656_CompleteAnalyzer.mqh"
#include "JM_GOLD_V680_LossRootCauseAnalyzer.mqh"

double OnTester()
{
   PrintCompleteAnalyzer();
   if(InpPrintLossRootCauseAnalyzer || InpPrintAllAnalyzers)
   {
      V656Trade tr[];
      int n=V656Collect(tr);
      PrintV680LossRootCause(tr,n);
   }
   return 0.0;
}
//+------------------------------------------------------------------+
