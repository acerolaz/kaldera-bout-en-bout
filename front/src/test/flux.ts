import { act } from "@testing-library/react";
import { vi } from "vitest";
import type { EvenementVue } from "@/api";

/** EventSource de test : on pilote l'ouverture, les événements et les coupures. */
export class FauxEventSource {
  static instances: FauxEventSource[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  url: string;
  ferme = false;
  readyState = FauxEventSource.CONNECTING;
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
    this.readyState = FauxEventSource.CLOSED;
  }
  ouvrir() {
    this.readyState = FauxEventSource.OPEN;
    act(() => this.onopen?.());
  }
  couper() {
    act(() => this.onerror?.()); // coupure réseau : le navigateur retente seul (CONNECTING)
  }
  /** Réponse non 200 (502 du proxy, 503) : le navigateur abandonne, readyState = CLOSED. */
  couperDefinitivement() {
    this.readyState = FauxEventSource.CLOSED;
    this.couper();
  }
  emettre(evenement: EvenementVue) {
    act(() => this.ecouteurs.get("avancement")?.(new MessageEvent("avancement", { data: JSON.stringify(evenement) })));
  }
}

export function simulerFlux() {
  FauxEventSource.instances = [];
  vi.stubGlobal("EventSource", FauxEventSource);
}
