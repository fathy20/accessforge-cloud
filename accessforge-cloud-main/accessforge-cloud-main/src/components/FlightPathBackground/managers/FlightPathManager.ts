import { Curves } from "../curves/Curves.ts";
import type {
  FlightPathParams,
  FlightPathManagerOptions,
} from "../common/Types.js";

export class FlightPathManager {
  private params: FlightPathParams;
  private getMergedCurves: () => Curves | null;
  private getFlightCount: () => number;
  private syncDashSize?: (value: number) => void;
  private syncGapSize?: (value: number) => void;
  private syncHidePath?: (value: boolean) => void;

  constructor(options: FlightPathManagerOptions) {
    this.params = options.params;
    this.getMergedCurves = options.getMergedCurves;
    this.getFlightCount = options.getFlightCount;
    this.syncDashSize = options.syncDashSize;
    this.syncGapSize = options.syncGapSize;
    this.syncHidePath = options.syncHidePath;
  }

  public applyDashPattern(): void {
    const mergedCurves = this.getMergedCurves();
    if (!mergedCurves) return;

    mergedCurves.setDashPattern(this.params.dashSize, this.params.gapSize);
    if (typeof mergedCurves.applyUpdates === "function") {
      mergedCurves.applyUpdates();
    }
  }

  public setDashSize(value: number): void {
    const numeric = Number(value);
    const dashSize = Number.isFinite(numeric) ? numeric : this.params.dashSize;

    if (this.params.dashSize === dashSize) {
      return;
    }

    this.params.dashSize = dashSize;
    this.applyDashPattern();

    if (typeof this.syncDashSize === "function") {
      this.syncDashSize(dashSize);
    }
  }

  public setGapSize(value: number): void {
    const numeric = Number(value);
    const gapSize = Number.isFinite(numeric) ? numeric : this.params.gapSize;

    if (this.params.gapSize === gapSize) {
      return;
    }

    this.params.gapSize = gapSize;
    this.applyDashPattern();

    if (typeof this.syncGapSize === "function") {
      this.syncGapSize(gapSize);
    }
  }

  public applyVisibility(): void {
    const mergedCurves = this.getMergedCurves();
    if (!mergedCurves) return;

    const visibleCount = this.params.hidePath ? 0 : this.getFlightCount();
    mergedCurves.setVisibleCurveCount(visibleCount);
  }

  public setHidePath(value: boolean): void {
    const boolValue = Boolean(value);
    if (this.params.hidePath !== boolValue) {
      this.params.hidePath = boolValue;
    }

    this.applyVisibility();

    if (typeof this.syncHidePath === "function") {
      this.syncHidePath(boolValue);
    }
  }
}
