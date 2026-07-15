/// <reference types="vite/client" />

interface ImportMetaEnv {
	readonly VITE_API_BASE_URL?: string;
	readonly VITE_SARAISE_MODE?: "development" | "self-hosted" | "saas";
}

interface ImportMeta {
	readonly env: ImportMetaEnv;
}
