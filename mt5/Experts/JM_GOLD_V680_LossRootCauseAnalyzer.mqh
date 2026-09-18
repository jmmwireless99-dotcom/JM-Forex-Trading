//+------------------------------------------------------------------+
//| JM_GOLD_V680_LossRootCauseAnalyzer.mqh                           |
//| Tester loss list for V6.77 — keep next to the EA.                |
//+------------------------------------------------------------------+
#ifndef JM_GOLD_V680_LOSS_ROOT_CAUSE
#define JM_GOLD_V680_LOSS_ROOT_CAUSE

void PrintV680LossRootCause(V656Trade &tr[],const int n)
{
   if(!InpPrintLossRootCauseAnalyzer && !InpPrintAllAnalyzers) return;
   int losses=0;
   Print("==============================================================");
   Print("JM GOLD V6.77 V680 loss list");
   for(int i=0;i<n;i++)
   {
      if(tr[i].profit>=0.0) continue;
      losses++;
      PrintFormat("LOSS #%d  %s  $%.2f  %s",
                  losses,
                  (tr[i].dir>0?"BUY":"SELL"),
                  tr[i].profit,
                  TimeToString(tr[i].timeOut,TIME_DATE|TIME_MINUTES));
   }
   PrintFormat("Losing exits: %d / %d",losses,n);
   Print("==============================================================");
}

#endif
//+------------------------------------------------------------------+
