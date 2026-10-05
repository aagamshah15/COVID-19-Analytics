import type { PageId, Theme } from "./state/app.svelte";

export const ICONS: Record<PageId, string> = {
  overview: "M3 20h18M6 16v-5M10 16V6M14 16v-8M18 16v-3",
  map: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3.6 9h16.8M3.6 15h16.8M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
  country: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  vaccines: "m17 3 4 4M19 5l-9.5 9.5M8 12l4 4M6.5 13.5 4 16l4 4 2.5-2.5M3 21l2-2",
  hospitals: "M3 21V8l9-5 9 5v13M9 21v-6h6v6M12 7v4M10 9h4",
  outlook: "M3 17l5-5 4 3 4-6 5 4M16 9h5v5",
  simulator: "M4 6h16M4 12h16M4 18h16M9 4v4M15 10v4M7 16v4",
  data: "M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6zM9 12l2 2 4-4",
};

export const MENU_ICON = "M4 7h16M4 12h16M4 17h16";
export const CLOSE_ICON = "M6 6l12 12M18 6 6 18";

export const THEMES: { id: Theme; label: string; icon: string }[] = [
  { id: "system", label: "Auto", icon: "M4 5h16v11H4zM8 20h8M12 16v4" },
  { id: "light", label: "Light", icon: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" },
  { id: "dark", label: "Dark", icon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" },
];
