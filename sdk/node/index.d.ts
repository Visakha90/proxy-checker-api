declare class ProxyChecker {
  constructor(options?: { apiKey?: string; baseUrl?: string });
  getProxies(options?: { type?: string; country?: string; anonymity?: string; alive?: boolean; ssl?: boolean; latencyLt?: number; limit?: number; page?: number }): Promise<any>;
  getRandom(options?: { type?: string; country?: string }): Promise<any>;
  getStats(): Promise<any>;
  getCountries(): Promise<any>;
  rotate(options?: { type?: string; country?: string }): Promise<any>;
  download(type?: string, format?: string): Promise<string>;
  getSpeedTiers(): Promise<any>;
  getLeaderboard(category?: string, limit?: number): Promise<any>;
  checkFingerprint(ip: string, port: number, type?: string): Promise<any>;
  gateway(url: string, options?: { method?: string; proxyType?: string; country?: string; speedTier?: string }): Promise<any>;
}

export = ProxyChecker;
