import React, { useState, useCallback } from 'react';

export interface WealthBreakdown {
  surface_rent: number;
  resource_rent: number;
  eco_rent: number;
  total_annual_rent: number;
  breakdown: Record<string, number>;
}

export interface WealthResponse {
  lat: number;
  lng: number;
  zone_id: string;
  wealth: WealthBreakdown;
}

export interface SurfaceRentData {
  [zoneId: string]: {
    rent_per_ha: number;
    stats: any;
  };
}

export function useWealthApi() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTotalWealth = useCallback(async (lat: number, lng: number, zoneId: string): Promise<WealthResponse | null> => {
    setIsLoading(true);
    setError(null);
    try {
      // Using the API proxy to reach the FastAPI backend
      const response = await fetch(`/backend/georgist/wealth?lat=${lat}&lng=${lng}&zone_id=${zoneId}`);
      if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
      return await response.json();
    } catch (err: any) {
      setError(err.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchSurfaceRentLayer = useCallback(async (): Promise<SurfaceRentData | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch('/backend/layers/georgist/surface-rent');
      if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
      const json = await response.json();
      return json.data;
    } catch (err: any) {
      setError(err.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchResourceRentLayer = useCallback(async (): Promise<any | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch('/backend/layers/georgist/resource-rent');
      if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
      return await response.json();
    } catch (err: any) {
      setError(err.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchEcoRentLayer = useCallback(async (): Promise<any | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch('/backend/layers/georgist/eco-rent');
      if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
      return await response.json();
    } catch (err: any) {
      setError(err.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    isLoading,
    error,
    fetchTotalWealth,
    fetchSurfaceRentLayer,
    fetchResourceRentLayer,
    fetchEcoRentLayer,
  };
}
