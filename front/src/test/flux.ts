import { act } from "@testing-library/react";
import { vi } from "vitest";
import type { EvenementVue } from "@/api";

/** EventSource de test : on pilote l'ouverture, les événements et les coupures. */
export class FauxEventSource {
  static instances: FauxEventSource[] = [];
  url: string;
  ferme = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private ecouteurs = new Map<string, (e: MessageEvent<string>) => void>();

  constructor(url: string) {
    this.url = url;
    FauxEventSource.instances.push(this);
  }
  addEventListener(type: string, ecouteur: (e: MessageEvent<string>) => void) {
    this.ecouteurs.set(type, ecouteur);
  }
  close() {
    this.ferme = true;
  }
  ouvrir() {
    act(() => this.onopen?.());
  }
  couper() {
    act(() => this.onerror?.());
  }
  emettre(evenement: EvenementVue) {
    act(() => this.ecouteurs.get("avancement")?.(new MessageEvent("avancement", { data: JSON.stringify(evenement) })));
  }
}

export function simulerFlux() {
  FauxEventSource.instances = [];
  vi.stubGlobal("EventSource", FauxEventSource);
}
