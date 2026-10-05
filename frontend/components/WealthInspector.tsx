import React, { useState } from 'react';
import { WealthBreakdown } from '../lib/useWealthApi';

interface WealthInspectorProps {
  isOpen: boolean;
  onClose: () => void;
  data: {
    lat: number;
    lng: number;
    zone_id: string;
    wealth: WealthBreakdown;
  } | null;
  isLoading: boolean;
}

export function WealthInspector({ isOpen, onClose, data, isLoading }: WealthInspectorProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-80 bg-white shadow-xl z-50 border-l border-slate-200 p-6 overflow-y-auto animate-in slide-in-from-right">
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 hover:bg-slate-100 rounded-full transition-colors"
      >
        ✕
      </button>

      <h2 className="text-xl font-bold mb-6 text-slate-900">National Wealth</h2>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : data ? (
        <div className="space-y-6">
          <div className="bg-slate-50 p-4 rounded-lg border border-slate-100">
            <p className="text-xs text-slate-500 uppercase font-semibold mb-1">Location</p>
            <p className="text-sm font-medium text-slate-700">Zone: {data.zone_id}</p>
            <p className="text-xs text-slate-400">{data.lat.toFixed(4)}, {data.lng.toFixed(4)}</p>
          </div>

          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-slate-600">🏠 Surface Rent</span>
              <span className="font-mono font-medium">£{data.wealth.surface_rent.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-600">🛢️ Resource Rent</span>
              <span className="font-mono font-medium">£{data.wealth.resource_rent.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-600">🌿 Eco Rent</span>
              <span className="font-mono font-medium">£{data.wealth.eco_rent.toLocaleString()}</span>
            </div>
            <div className="pt-4 border-t border-slate-200 flex justify-between items-end">
              <span className="text-lg font-bold text-slate-900">Total Wealth</span>
              <span className="text-2xl font-black text-blue-600">£{data.wealth.total_annual_rent.toLocaleString()}</span>
            </div>
          </div>

          {Object.keys(data.wealth.breakdown).length > 0 && (
            <div className="pt-6">
              <h3 className="text-sm font-bold text-slate-900 mb-3">Resource Breakdown</h3>
              <div className="space-y-2">
                {Object.entries(data.wealth.breakdown).map(([name, value]) => (
                  <div key={name} className="flex justify-between text-xs p-2 bg-slate-50 rounded border border-slate-100">
                    <span className="text-slate-600">{name}</span>
                    <span className="font-mono font-medium">£{value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-8 p-4 bg-blue-50 rounded-lg border border-blue-100">
            <p className="text-xs text-blue-800 leading-relaxed">
              This is an estimated annual economic rent based on Georgist principles of unearned increment from the commons.
            </p>
          </div>
        </div>
      ) : (
        <div className="text-center py-12 text-slate-400 italic">
          No data available for this location.
        </div>
      )}
    </div>
  );
}
