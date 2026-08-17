export const routes = {
  consultant: "/consultant",
} as const;

export type AppRoute = (typeof routes)[keyof typeof routes];
