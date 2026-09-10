//+------------------------------------------------------------------+
//| Live OK/WEAK/MALI panel for V6.1 — display only, no trade changes |
//+------------------------------------------------------------------+
#property strict

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
   double atr=0.0,bodyRatio=0.0,rangeAtr=0.0;
   bool haveSmall=GetSmallCandle(small,atr,bodyRatio,rangeAtr);

   int score=0,need=3;
   if(bias!=0)
   {
      score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);
      need=DynamicRequiredScore(bias,hour);
   }

   string h16=(InpBlockH16H17All && (hour==16 || hour==17))
              ? "MALI" : "OK";
   string buyLine=JM_SideAnalyzerLine(1,hour,bias,flow,haveSmall,adx,gapATR,rsi,bodyRatio,rangeAtr,atr,small);
   string sellLine=JM_SideAnalyzerLine(-1,hour,bias,flow,haveSmall,adx,gapATR,rsi,bodyRatio,rangeAtr,atr,small);

   // Recompute score with real ADX/gap for the status line (SideLine uses 0,0 for those extras)
   if(haveSmall && bias!=0)
      score=FlowScore(bias,flow,adx,gapATR,rsi,bodyRatio,rangeAtr);

   Comment("JM V6.1 ENTRY ANALYZER  ",InpMasterBuildTag,"\n",
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

// Recalculate BUY/SELL lines with real FlowScore (ADX + gap).
void LiveAnalyzerTickFull()
{
   LiveAnalyzerTick();
}
