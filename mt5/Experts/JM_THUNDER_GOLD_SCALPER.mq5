//+------------------------------------------------------------------+
//| JM_THUNDER_GOLD_SCALPER.mq5                                      |
//| JM Thunder GOLD Scalper V1.0.0                                   |
//| M5 swing break (thunder) + M1 small-candle trigger               |
//| NO grid, NO martingale, NO averaging. Hard SL+TP every trade.    |
//+------------------------------------------------------------------+
#define JMT_VERSION "1.0.0"
#property copyright "JM Tech Solution"
#property version   "1.00"
#property description "JM Thunder GOLD Scalper V1.0.0. One trade, hard SL/TP. Demo first."
#property strict

#include <Trade/Trade.mqh>
CTrade trade;

input string InpSymbol                 = "GOLD#";
input double InpLots                   = 0.01;
input long   InpMagic                  = 26100610;
input string InpBuildTag               = "THUNDER-V1.0.0-NOGRID";
input int    InpBrokerUtcOffsetHours   = 3;

input int    InpM5FastEMA              = 20;
input int    InpM5SlowEMA              = 50;
input int    InpM5ADXPeriod            = 14;
input double InpMinADX                 = 16.0;
input bool   InpUseChopFilter          = true;
input double InpMinM5GapATR            = 0.06;
input double InpWeakADXLevel           = 20.0;
input bool   InpBlockMidADX            = true;
input double InpBlockADXFrom           = 25.0;
input double InpBlockADXTo             = 35.0;
input bool   InpBlockBuyWeakEmaGap     = true;
input double InpBuyWeakGapATR          = 0.25;

input int    InpSwingLookback          = 12;
input double InpSwingBufferATR         = 0.05;
input int    InpThunderPersistBars     = 3;

input int    InpM1FastEMA              = 9;
input int    InpM1SlowEMA              = 21;
input int    InpM1RSIPeriod            = 14;
input int    InpM1ATRPeriod            = 14;
input double InpSmallBodyRatioMax      = 0.45;
input double InpMinSmallRangeATR       = 0.15;
input double InpMaxSmallRangeATR       = 0.80;
input double InpBreakBufferATR         = 0.05;
input bool   InpRequireM1Flow          = true;
input bool   InpUseFlowScore           = true;
input int    InpMinFlowScore           = 3;

input double InpBuyRSIMin              = 46.0;
input double InpBuyRSIMax              = 68.0;
input double InpSellRSIMin             = 32.0;
input double InpSellRSIMax             = 54.0;

input bool   InpUseFixedSLUsd          = true;
input double InpFixedSLUsd             = 15.0;
input double InpReferenceLot           = 0.01;
input bool   InpScaleUsdTargetsWithLot = true;
input bool   InpUseDynamicTP           = true;
input double InpTP_BaseUsd             = 30.0;
input double InpTP_StrongUsd           = 45.0;
input double InpDynADXStrong           = 32.0;
input double InpDynGapStrong           = 0.55;

input bool   InpUseV640Hours           = true;
input bool   InpSkipNfpFriday          = true;
input int    InpNfpStartHour           = 14;
input int    InpNfpEndHour             = 17;
input int    InpMinSecondsBetween      = 20;
input int    InpMaxSpreadPoints        = 0;
input bool   InpAllowBuy               = true;
input bool   InpAllowSell              = true;
input bool   InpShowPanel              = true;

string   g_symbol;
int      hM5Fast=INVALID_HANDLE,hM5Slow=INVALID_HANDLE,hM5ADX=INVALID_HANDLE,hM5ATR=INVALID_HANDLE;
int      hM1Fast=INVALID_HANDLE,hM1Slow=INVALID_HANDLE,hM1RSI=INVALID_HANDLE,hM1ATR=INVALID_HANDLE;
datetime g_lastEntryTime=0;
datetime g_lastSignalBar=0;
string   g_status="Starting";

#define JMT_DASH "JMT10_"

string JmtComment()
{
   return StringFormat("JM THUNDER GOLD SCALPER V%s",JMT_VERSION);
}

int PhtHour(const int serverHour)
{
   int add=8-InpBrokerUtcOffsetHours;
   return (serverHour+add+24)%24;
}

bool V640HourAllowed(const int dir,const int hour)
{
   if(!InpUseV640Hours) return true;
   int h=hour%24;
   if(h==4  && dir<0) return true;
   if(h==5)           return true;
   if(h==8)           return true;
   if(h==11 && dir<0) return true;
   if(h==12 && dir<0) return true;
   if(h==17 && dir>0) return true;
   if(h==19 && dir>0) return true;
   if(h==21 && dir<0) return true;
   if(h==22 && dir>0) return true;
   return false;
}

bool NfpBlocked()
{
   if(!InpSkipNfpFriday) return false;
   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   if(tm.day_of_week!=5) return false;
   if(tm.day>7) return false;
   return (tm.hour>=InpNfpStartHour && tm.hour<InpNfpEndHour);
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
   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return false;
   double point=SymbolInfoDouble(g_symbol,SYMBOL_POINT);
   if(point<=0.0) return false;
   return ((q.ask-q.bid)/point<=InpMaxSpreadPoints);
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

int M1Flow(double &rsi)
{
   double f,s;
   if(!Read1(hM1Fast,1,f) || !Read1(hM1Slow,1,s) || !Read1(hM1RSI,1,rsi))
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

bool ThunderSwing(const int dir,double &level,double &m5atr)
{
   if(dir==0) return false;
   if(!Read1(hM5ATR,1,m5atr) || m5atr<=0.0) return false;
   int need=InpSwingLookback+InpThunderPersistBars+1;
   if(need<4) need=4;
   MqlRates r[];
   if(CopyRates(g_symbol,PERIOD_M5,1,need,r)!=need) return false;
   ArraySetAsSeries(r,true);
   int persist=InpThunderPersistBars;
   if(persist<1) persist=1;
   double buffer=m5atr*InpSwingBufferATR;
   for(int i=0;i<persist;i++)
   {
      int from=i+1;
      int to=i+InpSwingLookback;
      if(to>=need) break;
      if(dir>0)
      {
         double swing=r[from].high;
         for(int k=from+1;k<=to;k++)
            if(r[k].high>swing) swing=r[k].high;
         if(r[i].high>swing+buffer && r[i].close>r[i].open)
         {
            level=swing;
            return true;
         }
      }
      else
      {
         double swing=r[from].low;
         for(int k=from+1;k<=to;k++)
            if(r[k].low<swing) swing=r[k].low;
         if(r[i].low<swing-buffer && r[i].close<r[i].open)
         {
            level=swing;
            return true;
         }
      }
   }
   return false;
}

double SelectTpUsd(const double adx,const double gapATR,const double lots)
{
   double tp=InpTP_BaseUsd;
   if(InpUseDynamicTP && adx>=InpDynADXStrong && gapATR>=InpDynGapStrong)
      tp=InpTP_StrongUsd;
   return tp*LotUsdScale(lots);
}

void DashDelete()
{
   const int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string name=ObjectName(0,i,0,-1);
      if(StringFind(name,JMT_DASH)==0)
         ObjectDelete(0,name);
   }
}

bool DashLabel(const string id,const int x,const int y,const string text,
               const color clr,const int fontSize=9)
{
   const string name=JMT_DASH+id;
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

bool DashBg(const int width,const int height)
{
   const string name=JMT_DASH"BG";
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
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrGold);
   return true;
}

string PosLine()
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
   return "Position: FLAT (waiting thunder)";
}

void UpdateDashboard()
{
   if(!InpShowPanel) return;
   if(MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION)) return;

   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   const double lots=NormalizeVolume(InpLots);
   double adx=0.0,gap=0.0,rsi=0.0,atr=0.0,body=0.0,rangeAtr=0.0,swing=0.0,m5atr=0.0;
   int bias=M5Bias(adx,gap);
   int flow=M1Flow(rsi);
   MqlRates small;
   bool smallOk=GetSmallCandle(small,atr,body,rangeAtr);
   bool thunder=(bias!=0 && ThunderSwing(bias,swing,m5atr));
   int score=0;
   if(bias!=0)
      score=FlowScore(bias,flow,adx,gap,rsi,body,rangeAtr);
   bool hourOk=(bias!=0 && V640HourAllowed(bias,tm.hour));
   bool nfp=NfpBlocked();
   color biasClr=clrSilver;
   if(bias>0) biasClr=clrLime;
   else if(bias<0) biasClr=clrOrangeRed;

   int x=16,y=26,dy=14;
   DashBg(430,290);
   DashLabel("T0",x,y,StringFormat("JM THUNDER GOLD SCALPER V%s | %s",JMT_VERSION,g_symbol),clrGold,10);
   y+=dy+2;
   DashLabel("T1",x,y,StringFormat("LOT %.2f | SL~$%.0f | TP~$%.0f | %s",
             lots,EffectiveSlUsd(lots),SelectTpUsd(adx,gap,lots),InpBuildTag),clrWhite);
   y+=dy;
   DashLabel("T2",x,y,StringFormat("Server %02d:%02d UTC+%d | PHT %02d:%02d | NFP %s",
             tm.hour,tm.min,InpBrokerUtcOffsetHours,PhtHour(tm.hour),tm.min,nfp?"BLOCK":"ok"),
             nfp?clrOrangeRed:clrLightGray);
   y+=dy;
   DashLabel("T3",x,y,StringFormat("BIAS %s | ADX %.1f | GapATR %.3f | Hour %s",
             (bias>0?"BUY":(bias<0?"SELL":"NONE")),adx,gap,hourOk?"ON":"OFF"),biasClr);
   y+=dy;
   DashLabel("T4",x,y,thunder
             ? StringFormat("THUNDER: YES | swing %.2f | persist %d M5",swing,InpThunderPersistBars)
             : "THUNDER: waiting M5 swing break",
             thunder?clrAqua:clrGray);
   y+=dy;
   DashLabel("T5",x,y,smallOk
             ? StringFormat("Small M1: YES | body %.0f%% | rangeATR %.2f",body*100.0,rangeAtr)
             : "Small M1: NO",
             smallOk?clrAqua:clrGray);
   y+=dy;
   DashLabel("T6",x,y,StringFormat("M1 flow %s | RSI %.1f | Score %d / %d",
             (flow>0?"UP":(flow<0?"DOWN":"flat")),rsi,score,InpMinFlowScore),clrWhite);
   y+=dy;
   DashLabel("T7",x,y,PosLine(),clrYellow);
   y+=dy;
   DashLabel("T8",x,y,"Status: "+g_status,clrWhite);
   ChartRedraw(0);
}

bool OpenTrade(const int dir,const double adx,const double gap,const string reason)
{
   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return false;
   const double lots=NormalizeVolume(InpLots);
   if(lots<=0.0) return false;

   double slUsd=EffectiveSlUsd(lots);
   double tpUsd=SelectTpUsd(adx,gap,lots);
   if(slUsd<=0.0) slUsd=InpFixedSLUsd;
   double slDist=MoneyToPriceDistance(slUsd,lots);
   double tpDist=MoneyToPriceDistance(tpUsd,lots);
   if(slDist<=0.0 || tpDist<=0.0)
   {
      g_status="USD->price distance failed";
      Print(g_status);
      return false;
   }
   slDist=RespectStops(slDist);
   tpDist=RespectStops(tpDist);

   int dg=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFilling(DetectFilling());

   bool ok=false;
   if(dir>0)
   {
      double sl=NormalizeDouble(q.ask-slDist,dg);
      double tp=NormalizeDouble(q.ask+tpDist,dg);
      ok=trade.Buy(lots,g_symbol,0.0,sl,tp,JmtComment());
   }
   else
   {
      double sl=NormalizeDouble(q.bid+slDist,dg);
      double tp=NormalizeDouble(q.bid-tpDist,dg);
      ok=trade.Sell(lots,g_symbol,0.0,sl,tp,JmtComment());
   }

   if(ok)
   {
      g_lastEntryTime=TimeCurrent();
      g_status=StringFormat("%s OPEN | Lot=%.2f SL~$%.0f TP~$%.0f",
                            dir>0?"BUY":"SELL",lots,slUsd,tpUsd);
      Print(g_status," | ",reason," | ",JmtComment());
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
   Print("JM THUNDER GOLD SCALPER V",JMT_VERSION," | ",InpBuildTag);
   Print("NO grid | NO martingale | NO averaging | one trade | hard SL+TP");
   PrintFormat("Lot=%.2f | SL~$%.0f | TP base $%.0f | GOLD# / XM UTC+%d",
               NormalizeVolume(InpLots),EffectiveSlUsd(NormalizeVolume(InpLots)),
               InpTP_BaseUsd,InpBrokerUtcOffsetHours);
   Print("Thunder = M5 swing break + M1 small-candle break + V640 hours");
   Print("==============================================================");
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
   DashDelete();
   Comment("");
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
         if(InpShowPanel) UpdateDashboard();
      }
   }

   if(HasOpenPosition()) return;
   if(!SpreadOK())
   {
      g_status="Spread too wide";
      return;
   }
   if(NfpBlocked())
   {
      g_status="NFP Friday block";
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

   double adx=0.0,gapATR=0.0;
   int bias=M5Bias(adx,gapATR);
   if(bias==0)
   {
      g_status="No M5 bias / weak ADX";
      return;
   }
   if(InpBlockMidADX && adx>=InpBlockADXFrom && adx<InpBlockADXTo)
   {
      g_status=StringFormat("MID ADX BLOCK | ADX=%.1f",adx);
      return;
   }
   if(InpBlockBuyWeakEmaGap && bias>0 && gapATR<InpBuyWeakGapATR)
   {
      g_status=StringFormat("BUY WEAK EMA GAP | GapATR=%.3f",gapATR);
      return;
   }

   double swing=0.0,m5atr=0.0;
   if(!ThunderSwing(bias,swing,m5atr))
   {
      g_status="Waiting for THUNDER (M5 swing break)";
      return;
   }

   double rsi=0.0;
   int flow=M1Flow(rsi);
   if(InpRequireM1Flow && flow!=bias)
   {
      g_status="M1 flow disagrees with M5";
      return;
   }

   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   if(!V640HourAllowed(bias,tm.hour))
   {
      g_status=StringFormat("V640 hour OFF | H%02d %s | PHT %02d:00",
                            tm.hour,bias>0?"BUY":"SELL",PhtHour(tm.hour));
      return;
   }

   int score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
   if(InpUseFlowScore && score<InpMinFlowScore)
   {
      g_status=StringFormat("Score %d < %d",score,InpMinFlowScore);
      return;
   }

   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return;
   double buffer=atr*InpBreakBufferATR;
   bool buyBreak=(q.ask>small.high+buffer);
   bool sellBreak=(q.bid<small.low-buffer);

   if(bias>0 && InpAllowBuy && buyBreak && rsi>=InpBuyRSIMin && rsi<=InpBuyRSIMax)
   {
      if(OpenTrade(1,adx,gapATR,StringFormat(
         "THUNDER BUY | swing=%.2f score=%d ADX=%.1f Gap=%.3f RSI=%.1f PHT=%02d",
         swing,score,adx,gapATR,rsi,PhtHour(tm.hour))))
         g_lastSignalBar=small.time;
      return;
   }
   if(bias<0 && InpAllowSell && sellBreak && rsi>=InpSellRSIMin && rsi<=InpSellRSIMax)
   {
      if(OpenTrade(-1,adx,gapATR,StringFormat(
         "THUNDER SELL | swing=%.2f score=%d ADX=%.1f Gap=%.3f RSI=%.1f PHT=%02d",
         swing,score,adx,gapATR,rsi,PhtHour(tm.hour))))
         g_lastSignalBar=small.time;
      return;
   }
}

double OnTester()
{
   if(!HistorySelect(0,TimeCurrent())) return 0.0;
   int n=0,wins=0,losses=0;
   double net=0.0;
   const int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0) continue;
      if(HistoryDealGetString(ticket,DEAL_SYMBOL)!=g_symbol) continue;
      if((long)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=InpMagic) continue;
      int entry=(int)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_INOUT && entry!=DEAL_ENTRY_OUT_BY)
         continue;
      double p=HistoryDealGetDouble(ticket,DEAL_PROFIT)
               +HistoryDealGetDouble(ticket,DEAL_SWAP)
               +HistoryDealGetDouble(ticket,DEAL_COMMISSION);
      n++;
      net+=p;
      if(p>=0.0) wins++; else losses++;
   }
   Print("==============================================================");
   Print("JM THUNDER GOLD SCALPER V",JMT_VERSION," tester");
   PrintFormat("Trades=%d Wins=%d Losses=%d Net=$%.2f",n,wins,losses,net);
   if(n>0) PrintFormat("WinRate=%.1f%%",100.0*(double)wins/(double)n);
   Print("==============================================================");
   return net;
}
//+------------------------------------------------------------------+
