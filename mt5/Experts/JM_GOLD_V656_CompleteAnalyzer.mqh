//+------------------------------------------------------------------+
//| JM_GOLD_V656_CompleteAnalyzer.mqh                                |
//| Tester report helper for V6.77 — keep next to the EA.            |
//+------------------------------------------------------------------+
#ifndef JM_GOLD_V656_COMPLETE_ANALYZER
#define JM_GOLD_V656_COMPLETE_ANALYZER

struct V656Trade
{
   datetime timeIn;
   datetime timeOut;
   int      dir;
   double   profit;
   double   volume;
   ulong    ticket;
};

int V656Collect(V656Trade &tr[])
{
   ArrayResize(tr,0);
   if(!HistorySelect(0,TimeCurrent())) return 0;
   const int total=HistoryDealsTotal();
   int n=0;
   for(int i=0;i<total;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if(ticket==0) continue;
      if(HistoryDealGetString(ticket,DEAL_SYMBOL)!=g_symbol) continue;
      if((long)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=InpMagic) continue;
      if((int)HistoryDealGetInteger(ticket,DEAL_ENTRY)!=DEAL_ENTRY_OUT &&
         (int)HistoryDealGetInteger(ticket,DEAL_ENTRY)!=DEAL_ENTRY_INOUT &&
         (int)HistoryDealGetInteger(ticket,DEAL_ENTRY)!=DEAL_ENTRY_OUT_BY)
         continue;
      int p=n;
      ArrayResize(tr,n+1);
      tr[p].ticket=ticket;
      tr[p].timeOut=(datetime)HistoryDealGetInteger(ticket,DEAL_TIME);
      tr[p].timeIn=tr[p].timeOut;
      tr[p].profit=HistoryDealGetDouble(ticket,DEAL_PROFIT)
                   +HistoryDealGetDouble(ticket,DEAL_SWAP)
                   +HistoryDealGetDouble(ticket,DEAL_COMMISSION);
      tr[p].volume=HistoryDealGetDouble(ticket,DEAL_VOLUME);
      long dtype=HistoryDealGetInteger(ticket,DEAL_TYPE);
      tr[p].dir=(dtype==DEAL_TYPE_SELL ? 1 : -1);
      n++;
   }
   return n;
}

void PrintCompleteAnalyzer()
{
   if(!InpPrintAllAnalyzers && !InpPrintAnalyzer) return;
   V656Trade tr[];
   int n=V656Collect(tr);
   int wins=0,losses=0,buys=0,sells=0;
   double net=0.0,grossW=0.0,grossL=0.0;
   for(int i=0;i<n;i++)
   {
      net+=tr[i].profit;
      if(tr[i].dir>0) buys++; else sells++;
      if(tr[i].profit>=0.0) { wins++; grossW+=tr[i].profit; }
      else { losses++; grossL+=tr[i].profit; }
   }
   Print("==============================================================");
   Print("JM GOLD V6.77 tester summary (V656 helper)");
   PrintFormat("Trades=%d  BUY=%d SELL=%d  Wins=%d Losses=%d",n,buys,sells,wins,losses);
   PrintFormat("Net=$%.2f  GrossW=$%.2f  GrossL=$%.2f",net,grossW,grossL);
   if(n>0)
      PrintFormat("WinRate=%.1f%%",100.0*(double)wins/(double)n);
   Print("==============================================================");
}

#endif
//+------------------------------------------------------------------+
