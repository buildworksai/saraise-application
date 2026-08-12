import "@testing-library/jest-dom/vitest";

function installStorageShim(name: "localStorage" | "sessionStorage") {
  if (globalThis[name]) return;

  const values = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => Array.from(values.keys()).at(index) ?? null,
    removeItem: (key: string) => {
      values.delete(key);
    },
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };

  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: storage,
  });
}

installStorageShim("localStorage");
installStorageShim("sessionStorage");
