/// <reference types="vite/client" />

import type { NavigateOptions, To } from "react-router";

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
    readonly VITE_API_PROXY_TARGET?: string;
    readonly VITE_DEV_SERVER_PORT?: string;
    readonly VITE_SARAISE_LICENSE_MODE?: "connected" | "isolated";
    readonly VITE_SARAISE_MODE?: "development" | "self-hosted" | "saas";
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

declare module "react-router" {
  interface NavigateFunction {
    (to: To, options?: NavigateOptions): void;
    (delta: number): void;
  }
}
