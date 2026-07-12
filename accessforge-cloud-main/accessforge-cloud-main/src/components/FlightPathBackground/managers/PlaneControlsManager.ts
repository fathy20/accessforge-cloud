import { Flight } from "../flights/Flight.ts";
import { PlanesShader } from "../planes/PlanesShader.ts";
import type { PlaneControlsManagerOptions } from "../common/Types.js";

export class PlaneControlsManager {
  private params: Record<string, any>;
  private getFlights: () => Flight[];
  private getPreGeneratedConfigs: () => Array<Record<string, any>>;
  private getMergedPanes: () => PlanesShader | null;
  private loadSvgTexture: () => Promise<{ texture: any; info: any }>;
  private initializeFlights: () => void;
  private syncPlaneSize?: (value: number) => void;
  private syncPlaneColor?: (value: number) => void;
  private syncPaneStyle?: (value: string) => void;
  private parsePlaneColor?: (value: any, fallback: number) => number;
  private fallbackPlaneColor: number;
  private syncAnimationSpeed?: (value: number) => void;
  private syncElevationOffset?: (value: number) => void;
  private syncHidePlane?: (value: boolean) => void;

  constructor(options: PlaneControlsManagerOptions) {
    this.params = options.params;
    this.getFlights = options.getFlights;
    this.getPreGeneratedConfigs = options.getPreGeneratedConfigs;
    this.getMergedPanes = options.getMergedPanes;
    this.loadSvgTexture = options.loadSvgTexture;
    this.initializeFlights = options.initializeFlights;
    this.syncPlaneSize = options.syncPlaneSize;
    this.syncPlaneColor = options.syncPlaneColor;
    this.syncPaneStyle = options.syncPaneStyle;
    this.parsePlaneColor = options.parsePlaneColor;
    this.fallbackPlaneColor = options.fallbackPlaneColor;
    this.syncAnimationSpeed = options.syncAnimationSpeed;
    this.syncElevationOffset = options.syncElevationOffset;
    this.syncHidePlane = options.syncHidePlane;
  }

  public setPlaneSize(value: number): void {
    const numeric = Number(value);
    const planeSize = Number.isFinite(numeric) ? numeric : this.params.planeSize;

    if (this.params.planeSize === planeSize) {
      return;
    }

    this.params.planeSize = planeSize;

    const flights = this.getFlights();
    flights.forEach((flight) => flight.setPaneSize(planeSize));

    const configs = this.getPreGeneratedConfigs();
    for (let i = 0; i < configs.length; i++) {
      const config = configs[i];
      if (config) {
        configs[i] = { ...config, paneSize: planeSize };
      }
    }

    if (typeof this.syncPlaneSize === "function") {
      this.syncPlaneSize(planeSize);
    }
  }

  public setPlaneColor(value: any): void {
    const normalized = this.normalizeColor(value);
    if (this.params.planeColor === normalized) {
      return;
    }

    this.params.planeColor = normalized;

    const flights = this.getFlights();
    flights.forEach((flight) => flight.setPaneColor(normalized));

    const configs = this.getPreGeneratedConfigs();
    for (let i = 0; i < configs.length; i++) {
      const config = configs[i];
      if (config) {
        configs[i] = { ...config, paneColor: normalized };
      }
    }

    if (typeof this.syncPlaneColor === "function") {
      this.syncPlaneColor(normalized);
    }
  }

  public setPaneStyle(style: string): void {
    const nextStyle = typeof style === "string" ? style : this.params.paneStyle;
    if (this.params.paneStyle !== nextStyle) {
      this.params.paneStyle = nextStyle;
    }

    if (typeof this.syncPaneStyle === "function") {
      this.syncPaneStyle(this.params.paneStyle);
    }

    const mergedPanes = this.getMergedPanes();

    if (this.params.paneStyle === "SVG") {
      this.loadSvgTexture()
        .then(({ texture, info }) => {
          const latestMerged = this.getMergedPanes();
          if (this.params.paneStyle === "SVG" && latestMerged) {
            latestMerged.setTexture(texture, info);
            this.getFlights().forEach((flight) =>
              flight.applyPaneTextureIndex?.(),
            );
          }
        })
        .catch(() => {});
    } else if (mergedPanes) {
      mergedPanes.setTexture(null);
    }

    this.initializeFlights();
  }

  public setAnimationSpeed(value: number): void {
    const numeric = Number(value);
    const speed = Number.isFinite(numeric) ? numeric : this.params.animationSpeed;

    if (this.params.animationSpeed === speed) {
      return;
    }

    this.params.animationSpeed = speed;
    this.applyAnimationSpeedMode();

    if (typeof this.syncAnimationSpeed === "function") {
      this.syncAnimationSpeed(speed);
    }
  }

  public setElevationOffset(value: number): void {
    const numeric = Number(value);
    const offset = Number.isFinite(numeric) ? numeric : this.params.elevationOffset;

    if (this.params.elevationOffset === offset) {
      return;
    }

    this.params.elevationOffset = offset;

    const flights = this.getFlights();
    const configs = this.getPreGeneratedConfigs();

    flights.forEach((flight) => {
      flight.setPaneElevation(offset);
    });

    for (let i = 0; i < configs.length; i++) {
      const config = configs[i];
      if (config) {
        configs[i] = { ...config, elevationOffset: offset };
      }
    }

    if (typeof this.syncElevationOffset === "function") {
      this.syncElevationOffset(offset);
    }
  }

  public setHidePlane(value: boolean): void {
    const shouldHide = Boolean(value);
    if (this.params.hidePlane !== shouldHide) {
      this.params.hidePlane = shouldHide;
    }

    const mergedPanes = this.getMergedPanes();
    if (mergedPanes) {
      const visibleCount = shouldHide ? 0 : this.getFlights().length;
      if (typeof mergedPanes.setActivePaneCount === "function") {
        mergedPanes.setActivePaneCount(visibleCount);
      }
      if (typeof mergedPanes.setPlanesVisible === "function") {
        mergedPanes.setPlanesVisible(!shouldHide);
      }
    }

    if (typeof this.syncHidePlane === "function") {
      this.syncHidePlane(shouldHide);
    }
  }

  public applyAnimationSpeedMode(): void {
    const flights = this.getFlights();
    const configs = this.getPreGeneratedConfigs();

    flights.forEach((flight, index) => {
      const config = configs[index] || {};
      const speed = this.resolveAnimationSpeed(config);
      flight.setAnimationSpeed(speed);
    });
  }

  public resolveAnimationSpeed(config: Record<string, any> = {}): number {
    if (this.params.randomSpeed) {
      if (typeof config._randomSpeed !== "number") {
        const base =
          typeof config.animationSpeed === "number"
            ? config.animationSpeed
            : this.generateRandomSpeed();
        config._randomSpeed = base;
      }
      return config._randomSpeed;
    }
    return this.params.animationSpeed;
  }

  private generateRandomSpeed(): number {
    const min = 0.03;
    const max = 0.25;
    return Math.random() * (max - min) + min;
  }

  private normalizeColor(value: any): number {
    let input = value;
    if (value && typeof value === "object") {
      const clamp = (component: any) => {
        const numeric = Number(component);
        if (!Number.isFinite(numeric)) return 0;
        return Math.max(0, Math.min(255, Math.round(numeric)));
      };
      const r = clamp(value.r ?? value.red);
      const g = clamp(value.g ?? value.green);
      const b = clamp(value.b ?? value.blue);
      input = (r << 16) | (g << 8) | b;
    }

    if (typeof this.parsePlaneColor === "function") {
      return this.parsePlaneColor(input, this.fallbackPlaneColor);
    }

    const numeric = Number(input);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
    if (typeof input === "string") {
      const normalized = input.trim().replace(/^#/, "");
      const parsed = parseInt(normalized, 16);
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
    return this.fallbackPlaneColor;
  }
}
