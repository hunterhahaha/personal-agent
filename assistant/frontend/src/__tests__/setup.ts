// Global test setup for vitest + jsdom + React Testing Library.
// Registers jest-dom matchers (toBeInTheDocument, etc.) and a minimal
// matchMedia polyfill so components relying on window.matchMedia do not crash.
import "@testing-library/jest-dom/vitest";

if (typeof window !== "undefined" && !("matchMedia" in window)) {
    Object.defineProperty(window, "matchMedia", {
        writable: true,
        value: (query: string) => ({
            matches: false,
            media: query,
            onchange: null,
            addListener: () => { },
            removeListener: () => { },
            addEventListener: () => { },
            removeEventListener: () => { },
            dispatchEvent: () => false,
        }),
    });
}
