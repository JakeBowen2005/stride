/** Shared with the server layout: boot code must not cross a client-module boundary. */
export type ThemeChoice = "system" | "light" | "dark";
export const THEME_KEY = "stride-theme";
export const THEME_QUERY = "(prefers-color-scheme: dark)";
export const DEFAULT_THEME: ThemeChoice = "dark";

export const THEME_BOOT_SCRIPT = `(function(){var d=true;try{var t=localStorage.getItem("${THEME_KEY}");d=t==="light"?false:t==="system"?matchMedia("${THEME_QUERY}").matches:true;}catch(e){}document.documentElement.classList.toggle("dark",d);})()`;
