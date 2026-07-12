import * as THREE from "three";
import { Flight } from "../flights/Flight.ts";
import { Curves } from "../curves/Curves.ts";
import { PlanesShader } from "../planes/PlanesShader.ts";
import { FlightUtils } from "../flights/FlightUtils.ts";
import type { Flight as FlightData } from "../common/Data.ts";
import type {
  FlightConfig,
  FlightParams,
  FlightControlsManagerOptions,
} from "../common/Types.js";

export class FlightControlsManager {
  private params: FlightParams;
  private maxFlights: number;
  private getFlights: () => Flight[];
  private getPreGeneratedConfigs: () => FlightConfig[];
  private getMergedCurves: () => Curves | null;
  private getMergedPanes?: () => PlanesShader | null;
  private ensurePlaneDefaults: (
    config?: Partial<FlightConfig>,
  ) => FlightConfig;
  private assignRandomPlane: (
    config?: Partial<FlightConfig>,
  ) => FlightConfig;
  private resolvePaneColor: (config?: Partial<FlightConfig>) => number;
  private resolveAnimationSpeed: (config?: Partial<FlightConfig>) => number;
  private createFlightFromConfig: (config: FlightConfig, index: number) => Flight;
  private updatePathVisibility: () => void;
  private updatePlaneVisibility: () => void;
  private syncFlightCount?: (value: number) => void;
  private syncReturnFlight?: (value: boolean) => void;

  constructor(options: FlightControlsManagerOptions) {
    this.params = options.params;
    this.maxFlights = options.maxFlights;
    this.getFlights = options.getFlights;
    this.getPreGeneratedConfigs = options.getPreGeneratedConfigs;
    this.getMergedCurves = options.getMergedCurves;
    this.getMergedPanes = options.getMergedPanes;
    this.ensurePlaneDefaults = options.ensurePlaneDefaults;
    this.assignRandomPlane = options.assignRandomPlane;
    this.resolvePaneColor = options.resolvePaneColor;
    this.resolveAnimationSpeed = options.resolveAnimationSpeed;
    this.createFlightFromConfig = options.createFlightFromConfig;
    this.updatePathVisibility = options.updatePathVisibility;
    this.updatePlaneVisibility = options.updatePlaneVisibility;
    this.syncFlightCount = options.syncFlightCount;
    this.syncReturnFlight = options.syncReturnFlight;
  }

  public updateFlightCount(target: number): void {
    const flights = this.getFlights();
    const preGeneratedConfigs = this.getPreGeneratedConfigs();
    const mergedCurves = this.getMergedCurves();

    const currentCount = flights.length;
    const availableConfigs =
      preGeneratedConfigs.length > 0
        ? preGeneratedConfigs.length
        : this.maxFlights;
    const desiredCount = Math.min(Math.max(target, 0), availableConfigs);

    this.params.numFlights = desiredCount;

    if (desiredCount > currentCount) {
      for (let i = currentCount; i < desiredCount; i++) {
        let baseConfig: FlightConfig;

        if (preGeneratedConfigs.length) {
          const configIndex = i % preGeneratedConfigs.length;
          baseConfig = this.ensurePlaneDefaults(
            preGeneratedConfigs[configIndex],
          );
          baseConfig.returnFlight = this.params.returnFlight;
          preGeneratedConfigs[configIndex] = baseConfig;
        } else {
          baseConfig = this.assignRandomPlane(
            FlightUtils.generateRandomFlightConfig({ numControlPoints: 2 }),
          );
          baseConfig.returnFlight = this.params.returnFlight;
        }

        const flightConfig: FlightConfig = {
          ...baseConfig,
          controlPoints: FlightUtils.cloneControlPoints(
            baseConfig.controlPoints,
          ),
          segmentCount: this.params.segmentCount,
          curveColor: baseConfig.curveColor,
          paneSize: this.params.planeSize,
          paneColor: this.resolvePaneColor(baseConfig),
          animationSpeed: this.resolveAnimationSpeed(baseConfig),
          elevationOffset:
            baseConfig.elevationOffset !== undefined
              ? baseConfig.elevationOffset
              : this.params.elevationOffset,
          paneTextureIndex: baseConfig.paneTextureIndex,
          returnFlight: this.params.returnFlight,
        };

        const flight = this.createFlightFromConfig(flightConfig, i);
        flights.push(flight);
      }

      if (mergedCurves && typeof mergedCurves.applyUpdates === "function") {
        mergedCurves.applyUpdates();
      }
    } else if (desiredCount < currentCount) {
      const flightsToRemove = flights.splice(desiredCount);
      flightsToRemove.forEach((flight) => flight.remove());
    }

    this.updatePathVisibility();
    this.updatePlaneVisibility();

    if (typeof this.syncFlightCount === "function") {
      this.syncFlightCount(this.params.numFlights);
    }
  }

  public setReturnFlight(value: boolean): void {
    const flights = this.getFlights();
    const preGeneratedConfigs = this.getPreGeneratedConfigs();
    const nextValue = Boolean(value);
    const previousValue = this.params.returnFlight;

    this.params.returnFlight = nextValue;

    preGeneratedConfigs.forEach((config) => {
      if (config) {
        config.returnFlight = nextValue;
      }
    });

    flights.forEach((flight) => {
      flight.setReturnFlight(nextValue);
    });

    if (this.getMergedPanes) {
      const mergedPanes = this.getMergedPanes();
      if (mergedPanes && typeof mergedPanes.setReturnMode === "function") {
        mergedPanes.setReturnMode(nextValue);
      }
    }

    if (
      typeof this.syncReturnFlight === "function" &&
      previousValue !== nextValue
    ) {
      this.syncReturnFlight(nextValue);
    }
  }
}
