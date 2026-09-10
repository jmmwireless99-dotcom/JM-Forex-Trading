//+------------------------------------------------------------------+
//| JM_GOLD_EMA200_STOCH_SCALPER.mq5                                 |
//| Clean gold scalp: EMA200 trend + Stochastic 5,3,3 + small candle |
//| Scale-out: SL $2-5 · TP1 $5 (50%+BE) · TP2 $10 · TP3 $15         |
//| Single file — F7 this only. Do not attach with V6.1 on same chart.|
//+------------------------------------------------------------------+
#property copyright "JM Tech Solution"
#property version   "1.00"
#property description "GOLD# EMA200 + Stoch 5,3,3 scalper. Scale-out $5/$10/$15. Use 0.03 lot for 3 legs."

#include <Trade/Trade.mqh>
CTrade trade;

input string InpSymbol           = "GOLD#";
input double InpLots             = 0.03;      // 0.03 = three 0.01 legs. 0.01 cannot scale-out (broker min lot)
input long   InpMagic            = 26091080;
input string InpBuildTag         = "EMA200-STOCH-SCALEOUT-v1";

input int    InpEMA              = 200;
input int    InpStochK           = 5;
input int    InpStochD           = 3;
input int    InpStochSlow        = 3;
input double InpStochOS          = 20.0;      // oversold
input double InpStochOB          = 80.0;      // overbought

input int    InpPullbackBars     = 2;         // small opposite candles before trigger
input double InpSmallBodyMax     = 0.55;      // body/range max = "maliit na kandila"
input double InpMinRangeUsd      = 0.20;      // skip ultra-doji noise

input double InpSLUsd            = 3.50;      // gold $ behind entry ($2–$5). 50–150 pips TP = $5/$10/$15
input double InpTP1Usd           = 5.00;      // gold $: close ~50%, SL → breakeven
input double InpTP2Usd           = 10.00;     // gold $: close next min-lot
input double InpTP3Usd           = 15.00;     // gold $: close rest (hard TP on order)
input double InpBEOffsetUsd      = 0.20;      // gold $ past entry after TP1

input bool   InpUseNySession     = true;
input int    InpSessionStartHour = 14;        // XM GMT+2 ≈ PH 8:00 PM (NY)
input int    InpSessionEndHour   = 23;        // exclusive
input bool   InpSkipNfpFriday    = true;
input int    InpNfpStartHour     = 14;        // broker hour — first Friday block
input int    InpNfpEndHour       = 17;

input int    InpMinSecondsBetween= 30;
input int    InpMaxSpreadPoints  = 0;         // 0 = off
input bool   InpAllowBuy         = true;
input bool   InpAllowSell        = true;
input bool   InpShowPanel        = true;

string   g_symbol;
int      hEMA = INVALID_HANDLE;
int      hStoch = INVALID_HANDLE;
datetime g_lastBar = 0;
datetime g_lastEntry = 0;
string   g_status = "Starting";
ulong    g_ticket = 0;
bool     g_tp1 = false;
bool     g_tp2 = false;

bool ReadBuf(const int handle,const int buf,const int shift,double &v)
{
   double a[1];
   if(CopyBuffer(handle,buf,shift,1,a)!=1) return false;
   v=a[0];
   return true;
}

// Gold quote $ (XAUUSD): $1.00 price = 10 pips. SL/TP/scale-out use this, not account P/L.
double RespectStops(const double dist)
{
   long lvl=(long)SymbolInfoInteger(g_symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double minD=lvl*SymbolInfoDouble(g_symbol,SYMBOL_POINT);
   return MathMax(dist,minD);
}

double NormVol(double v)
{
   double vmin=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_STEP);
   if(step<=0.0) step=0.01;
   if(vmin<=0.0) vmin=0.01;
   v=MathFloor(v/step+1e-8)*step;
   if(v<vmin) return 0.0;
   if(v>vmax) v=vmax;
   return NormalizeDouble(v,2);
}

bool SpreadOK()
{
   if(InpMaxSpreadPoints<=0) return true;
   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return false;
   double pt=SymbolInfoDouble(g_symbol,SYMBOL_POINT);
   if(pt<=0.0) return true;
   return ((q.ask-q.bid)/pt)<=InpMaxSpreadPoints;
}

bool InNySession(const int hour)
{
   if(!InpUseNySession) return true;
   if(InpSessionStartHour<InpSessionEndHour)
      return (hour>=InpSessionStartHour && hour<InpSessionEndHour);
   return (hour>=InpSessionStartHour || hour<InpSessionEndHour);
}

bool NfpBlocked()
{
   if(!InpSkipNfpFriday) return false;
   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   if(tm.day_of_week!=5) return false;     // Friday
   if(tm.day>7) return false;              // first Friday
   return (tm.hour>=InpNfpStartHour && tm.hour<InpNfpEndHour);
}

bool HasOurPosition()
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

bool SelectOurPosition()
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

double FavorableMove()
{
   if(!SelectOurPosition()) return 0.0;
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   long type=PositionGetInteger(POSITION_TYPE);
   double bid=SymbolInfoDouble(g_symbol,SYMBOL_BID);
   double ask=SymbolInfoDouble(g_symbol,SYMBOL_ASK);
   if(type==POSITION_TYPE_BUY) return bid-entry;
   return entry-ask;
}

bool IsSmallCandle(const MqlRates &b)
{
   double range=b.high-b.low;
   if(range<InpMinRangeUsd) return false;
   double body=MathAbs(b.close-b.open);
   return (body/range)<=InpSmallBodyMax;
}

bool BullBar(const MqlRates &b) { return b.close>b.open; }
bool BearBar(const MqlRates &b) { return b.close<b.open; }

bool PullbackSmall(const int dir,const MqlRates &bars[])
{
   int need=InpPullbackBars;
   if(need<1) need=1;
   if(ArraySize(bars)<need+2) return false;
   for(int i=2;i<2+need;i++)
   {
      if(!IsSmallCandle(bars[i])) return false;
      if(dir>0 && !BearBar(bars[i])) return false;   // BUY pullback = small red
      if(dir<0 && !BullBar(bars[i])) return false;   // SELL pullback = small green
   }
   return true;
}

int OnInit()
{
   g_symbol=(InpSymbol=="" ? _Symbol : InpSymbol);
   if(!SymbolSelect(g_symbol,true)) return INIT_FAILED;

   hEMA=iMA(g_symbol,PERIOD_M1,InpEMA,0,MODE_EMA,PRICE_CLOSE);
   hStoch=iStochastic(g_symbol,PERIOD_M1,InpStochK,InpStochD,InpStochSlow,MODE_SMA,STO_LOWHIGH);
   if(hEMA==INVALID_HANDLE || hStoch==INVALID_HANDLE)
      return INIT_FAILED;

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(40);
   trade.SetTypeFillingBySymbol(g_symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hEMA!=INVALID_HANDLE) IndicatorRelease(hEMA);
   if(hStoch!=INVALID_HANDLE) IndicatorRelease(hStoch);
   Comment("");
}

void Panel(const string extra)
{
   if(!InpShowPanel) return;
   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   Comment("JM GOLD EMA200 + STOCH  ",InpBuildTag,"\n",
           "M1  EMA",IntegerToString(InpEMA),"  Stoch ",
           IntegerToString(InpStochK),",",IntegerToString(InpStochD),",",IntegerToString(InpStochSlow),"\n",
           "Lots ",DoubleToString(InpLots,2),
           "  SL $",DoubleToString(InpSLUsd,2),
           "  TP $",DoubleToString(InpTP1Usd,0),"/",
           DoubleToString(InpTP2Usd,0),"/",DoubleToString(InpTP3Usd,0),"\n",
           "Hour H",IntegerToString(tm.hour),
           "  session ",(InNySession(tm.hour)?"OK":"WAIT"),
           "  NFP ",(NfpBlocked()?"BLOCK":"ok"),"\n",
           extra,"\n",
           "Status: ",g_status);
}

void ManageScaleOut()
{
   if(!SelectOurPosition())
   {
      g_ticket=0;
      g_tp1=false;
      g_tp2=false;
      return;
   }

   ulong ticket=(ulong)PositionGetInteger(POSITION_TICKET);
   if(ticket!=g_ticket)
   {
      g_ticket=ticket;
      g_tp1=false;
      g_tp2=false;
   }

   double move=FavorableMove();
   double vol=PositionGetDouble(POSITION_VOLUME);
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   long type=PositionGetInteger(POSITION_TYPE);
   double vmin=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MIN);
   if(vmin<=0.0) vmin=0.01;

   int dg=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);

   // Tiny lot: cannot partial — close all at TP1 gold-$
   if(vol<=vmin+1e-8)
   {
      if(move>=InpTP1Usd)
      {
         trade.PositionClose(ticket);
         g_status="CLOSE tiny-lot at TP1 (gold $)";
      }
      return;
   }

   if(!g_tp1 && move>=InpTP1Usd)
   {
      // 0.03 → close 0.01 (50% floors to min lot). Never send 0.015.
      double closeVol=NormVol(vol*0.5);
      if(closeVol<vmin) closeVol=vmin;
      if(closeVol>0.0 && closeVol<vol)
      {
         if(trade.PositionClosePartial(ticket,closeVol))
         {
            g_tp1=true;
            double sl=entry;
            if(type==POSITION_TYPE_BUY) sl=NormalizeDouble(entry+InpBEOffsetUsd,dg);
            else sl=NormalizeDouble(entry-InpBEOffsetUsd,dg);
            if(SelectOurPosition())
               trade.PositionModify((ulong)PositionGetInteger(POSITION_TICKET),sl,PositionGetDouble(POSITION_TP));
            g_status=StringFormat("TP1 +$%.0f gold closed %.2f · SL→BE",InpTP1Usd,closeVol);
         }
      }
      return;
   }

   if(g_tp1 && !g_tp2 && move>=InpTP2Usd)
   {
      if(!SelectOurPosition()) return;
      vol=PositionGetDouble(POSITION_VOLUME);
      ticket=(ulong)PositionGetInteger(POSITION_TICKET);
      double closeVol=NormVol(MathMin(vmin,vol-vmin));
      if(vol-closeVol<vmin) closeVol=NormVol(vol-vmin);
      if(closeVol>=vmin && closeVol<vol)
      {
         if(trade.PositionClosePartial(ticket,closeVol))
         {
            g_tp2=true;
            g_status=StringFormat("TP2 +$%.0f gold closed %.2f",InpTP2Usd,closeVol);
         }
      }
      else
      {
         trade.PositionClose(ticket);
         g_tp2=true;
         g_status="TP2 close remainder";
      }
      return;
   }

   if(g_tp1 && move>=InpTP3Usd)
   {
      if(SelectOurPosition())
      {
         trade.PositionClose((ulong)PositionGetInteger(POSITION_TICKET));
         g_status=StringFormat("TP3 +$%.0f gold full close",InpTP3Usd);
      }
   }
}

bool OpenDir(const int dir,const string why)
{
   MqlTick q;
   if(!SymbolInfoTick(g_symbol,q)) return false;
   double lots=NormVol(InpLots);
   if(lots<=0.0) { g_status="Lots below broker min"; return false; }

   double slDist=RespectStops(InpSLUsd);
   double tpDist=RespectStops(InpTP3Usd);
   if(slDist<=0.0 || tpDist<=0.0) return false;

   int dg=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);
   trade.SetExpertMagicNumber(InpMagic);
   bool ok=false;
   if(dir>0)
   {
      double sl=NormalizeDouble(q.ask-slDist,dg);
      double tp=NormalizeDouble(q.ask+tpDist,dg);
      ok=trade.Buy(lots,g_symbol,0.0,sl,tp,why);
   }
   else
   {
      double sl=NormalizeDouble(q.bid+slDist,dg);
      double tp=NormalizeDouble(q.bid-tpDist,dg);
      ok=trade.Sell(lots,g_symbol,0.0,sl,tp,why);
   }
   if(ok)
   {
      g_lastEntry=TimeCurrent();
      g_tp1=false;
      g_tp2=false;
      g_status=StringFormat("%s OPEN SL$%.2f TP3$%.2f | %s",
                            dir>0?"BUY":"SELL",InpSLUsd,InpTP3Usd,why);
      Print(g_status);
   }
   else
      g_status="Order fail "+trade.ResultRetcodeDescription();
   return ok;
}

void OnTick()
{
   ManageScaleOut();
   if(HasOurPosition())
   {
      Panel("IN TRADE — scale-out managing");
      return;
   }
   if(!SpreadOK()) { g_status="Spread too wide"; Panel(""); return; }
   if(NfpBlocked()) { g_status="NFP Friday blackout"; Panel(""); return; }

   MqlDateTime tm;
   TimeToStruct(TimeCurrent(),tm);
   if(!InNySession(tm.hour))
   {
      g_status="Wait NY session (PH 8PM+)";
      Panel("");
      return;
   }
   if((TimeCurrent()-g_lastEntry)<InpMinSecondsBetween) return;

   datetime bar=iTime(g_symbol,PERIOD_M1,1);
   if(bar==0 || bar==g_lastBar) { Panel("Waiting M1 close"); return; }

   MqlRates r[];
   ArraySetAsSeries(r,true);
   if(CopyRates(g_symbol,PERIOD_M1,0,InpPullbackBars+6,r)<InpPullbackBars+4)
   {
      g_status="Need M1 history";
      Panel("");
      return;
   }

   double ema=0,k1=0,d1=0,k2=0,d2=0;
   if(!ReadBuf(hEMA,0,1,ema)) return;
   if(!ReadBuf(hStoch,0,1,k1) || !ReadBuf(hStoch,1,1,d1)) return;
   if(!ReadBuf(hStoch,0,2,k2) || !ReadBuf(hStoch,1,2,d2)) return;

   double px=r[1].close;
   bool up=(px>ema);
   bool down=(px<ema);
   bool smallTrig=IsSmallCandle(r[1]);

   string why=StringFormat("EMA200=%.2f Stoch %.1f/%.1f",ema,k1,d1);

   bool buyTrig=up && InpAllowBuy && smallTrig && BullBar(r[1]) &&
                PullbackSmall(1,r) &&
                (k2<=InpStochOS && d2<=InpStochOS) &&
                (k1>d1) && (k1>k2);

   bool sellTrig=down && InpAllowSell && smallTrig && BearBar(r[1]) &&
                 PullbackSmall(-1,r) &&
                 (k2>=InpStochOB && d2>=InpStochOB) &&
                 (k1<d1) && (k1<k2);

   if(buyTrig)
   {
      if(OpenDir(1,"BUY pullback+stoch-OS-cross | "+why))
         g_lastBar=bar;
      Panel(why);
      return;
   }
   if(sellTrig)
   {
      if(OpenDir(-1,"SELL pullback+stoch-OB-cross | "+why))
         g_lastBar=bar;
      Panel(why);
      return;
   }

   g_lastBar=bar;
   g_status="Wait setup (trend+small pullback+stoch cross)";
   Panel(why+"  trig "+(smallTrig?"small":"fat")+(up?" aboveEMA":down?" belowEMA":""));
}
//+------------------------------------------------------------------+
