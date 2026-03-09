import React, { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { BarChart3 } from "lucide-react";

export default function LiveChart() {
  const chartRef = useRef<HTMLDivElement>(null);
  const { data: candles } = useQuery({
    queryKey: ["candles"],
    queryFn: () => api.getCandles(500),
    refetchInterval: 10000,
  });
  const { data: regime } = useQuery({ queryKey: ["regime"], queryFn: api.getRegime });

  useEffect(() => {
    if (!chartRef.current || !candles?.length) return;

    let chart: any = null;
    import("lightweight-charts").then(({ createChart }) => {
      if (!chartRef.current) return;
      chartRef.current.innerHTML = "";

      chart = createChart(chartRef.current, {
        width: chartRef.current.clientWidth,
        height: chartRef.current.clientHeight,
        layout: { background: { color: "#0a0e17" }, textColor: "#9ca3af" },
        grid: {
          vertLines: { color: "#1a2332" },
          horzLines: { color: "#1a2332" },
        },
        crosshair: { mode: 0 },
        timeScale: { timeVisible: true, secondsVisible: false },
      });

      const candleSeries = chart.addCandlestickSeries({
        upColor: "#10b981",
        downColor: "#ef4444",
        borderUpColor: "#10b981",
        borderDownColor: "#ef4444",
        wickUpColor: "#10b981",
        wickDownColor: "#ef4444",
      });

      const chartData = candles.map((c: any) => ({
        time: Math.floor(new Date(c.ts).getTime() / 1000) as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

      candleSeries.setData(chartData);

      // Volume
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });

      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });

      const volData = candles.map((c: any) => ({
        time: Math.floor(new Date(c.ts).getTime() / 1000) as any,
        value: c.volume,
        color: c.close >= c.open ? "#10b98133" : "#ef444433",
      }));

      volumeSeries.setData(volData);
      chart.timeScale().fitContent();
    });

    return () => { if (chart) chart.remove(); };
  }, [candles]);

  return (
    <div className="space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-cyan-400" />
          <h1 className="text-xl font-bold">Live Chart - MES 5min</h1>
        </div>
        {regime && (
          <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300">
            Regime: {regime.regime?.replace("_", " ").toUpperCase()} ({((regime.confidence || 0) * 100).toFixed(0)}%)
          </span>
        )}
      </div>
      <div ref={chartRef} className="flex-1 min-h-[500px] bg-gray-950 rounded-lg border border-gray-800" />
    </div>
  );
}
