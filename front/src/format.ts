const EUROS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const HEURE = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });

export const euros = (montant: number): string => EUROS.format(montant);
export const heure = (iso: string): string => HEURE.format(new Date(iso));
export function duree(secondes: number): string {
  const s = Math.max(0, Math.round(secondes));
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}
