import * as THREE from "three";
import type { Geolocation, Flight as FlightData } from "../common/Data.ts";
import { latLngToVector3 } from "../common/Utils.ts";
import { Flight } from "./Flight.ts";
import { Curves } from "../curves/Curves.ts";
import { PlanesShader } from "../planes/PlanesShader.ts";
import type {
  Bounds,
  RandomCurveOptions,
  ColorOptions,
  FlightConfigOptions,
  FlightConfig,
  GradientColorConfig,
  PlaneEntry,
} from "../common/Types.js";

/**
 * Utility functions for generating flight paths and control points
 */
export class FlightUtils {
  /**
   * Create a gradient color configuration for a flight.
   * @param departure - Departure geolocation
   * @returns Gradient configuration or null if no departure
   */
  static createGradientColorConfig(
    departure: Geolocation | null | undefined,
  ): GradientColorConfig | null {
    if (!departure) {
      return null;
    }

    return {
      type: "gradient",
      departureLat: departure.lat,
      departureLng: departure.lng,
    };
  }

  /**
   * Clone an array of control points.
   * @param points - Points to clone
   * @returns Cloned points
   */
  static cloneControlPoints(points: THREE.Vector3[]): THREE.Vector3[] {
    return points.map((point) => point.clone());
  }

  /**
   * Ensure all control points stay above a minimum altitude.
   * @param points - Control points to adjust
   * @param radius - Base sphere radius
   * @param minAltitude - Minimum altitude above the sphere surface
   * @returns Adjusted control points
   */
  static ensureMinimumCurveAltitude(
    points: THREE.Vector3[],
    radius: number,
    minAltitude: number,
  ): THREE.Vector3[] {
    const safeRadius = radius + minAltitude;
    return points.map((point) => {
      if (!point) {
        return point;
      }
      const adjusted = point.clone();
      const length = adjusted.length();
      if (length > 0 && length < safeRadius) {
        adjusted.normalize().multiplyScalar(safeRadius);
      }
      return adjusted;
    });
  }

  /**
   * Normalize raw control points into four evenly-sampled points.
   * @param points - Input control points
   * @param radius - Target sphere radius
   * @param minAltitude - Minimum altitude above the sphere surface
   * @returns Four normalized control points
   */
  static normalizeControlPoints(
    points: THREE.Vector3[],
    radius: number,
    minAltitude: number,
  ): THREE.Vector3[] {
    const sourcePoints =
      points && points.length ? this.cloneControlPoints(points) : [];
    if (sourcePoints.length === 4) {
      return this.ensureMinimumCurveAltitude(sourcePoints, radius, minAltitude);
    }

    if (!sourcePoints.length) {
      return [];
    }

    const curve = new THREE.CatmullRomCurve3(sourcePoints);
    const sampledPoints = [
      curve.getPoint(0.0),
      curve.getPoint(0.333),
      curve.getPoint(0.666),
      curve.getPoint(1.0),
    ];

    return this.ensureMinimumCurveAltitude(sampledPoints, radius, minAltitude);
  }

  /**
   * Generate a random point inside a sphere centered at the origin.
   * @param radius - Sphere radius
   * @returns Random point inside sphere
   */
  static randomPointInSphere(radius: number): THREE.Vector3 {
    const u = Math.random();
    const v = Math.random();
    const theta = 2 * Math.PI * u;
    const phi = Math.acos(2 * v - 1);
    const r = radius * Math.cbrt(Math.random());
    const sinPhi = Math.sin(phi);

    return new THREE.Vector3(
      r * sinPhi * Math.cos(theta),
      r * sinPhi * Math.sin(theta),
      r * Math.cos(phi),
    );
  }

  /**
   * Clamp a vector to lie within a sphere.
   * @param vector - Vector to clamp (mutated in place)
   * @param radius - Sphere radius
   * @param center - Sphere center
   * @returns The clamped vector
   */
  static clampToSphere(
    vector: THREE.Vector3,
    radius: number,
    center: THREE.Vector3,
  ): THREE.Vector3 {
    const offset = vector.clone().sub(center);
    const radiusSq = radius * radius;

    if (offset.lengthSq() > radiusSq) {
      offset.setLength(radius);
      vector.copy(offset.add(center));
    }

    return vector;
  }

  /**
   * Options for generating parabolic control points between two geolocations.
   */
  static generateParabolicControlPoints(
    departure: Geolocation,
    arrival: Geolocation,
    options: {
      radius: number;
      takeoffOffset: number;
      minCurveAltitude: number;
      minCruiseAltitude: number;
      maxCruiseAltitude: number;
    },
  ): THREE.Vector3[] {
    const {
      radius,
      takeoffOffset,
      minCurveAltitude,
      minCruiseAltitude,
      maxCruiseAltitude,
    } = options;

    const surfaceOffset = Math.max(takeoffOffset, minCurveAltitude);
    const cruiseMin = Math.max(minCruiseAltitude, surfaceOffset + 5);

    const origin = latLngToVector3(departure.lat, departure.lng, radius);
    const destination = latLngToVector3(arrival.lat, arrival.lng, radius);

    const startSurface = origin
      .clone()
      .normalize()
      .multiplyScalar(radius + surfaceOffset);
    const endSurface = destination
      .clone()
      .normalize()
      .multiplyScalar(radius + surfaceOffset);

    const distance = startSurface.distanceTo(endSurface);
    const maxDistance = radius * Math.PI;
    const distanceRatio = Math.min(distance / (maxDistance * 0.3), 1);
    const cruiseAltitude =
      cruiseMin +
      (maxCruiseAltitude - cruiseMin) * Math.pow(distanceRatio, 0.7);

    const climbPoint1 = startSurface
      .clone()
      .lerp(endSurface, 0.2)
      .normalize()
      .multiplyScalar(radius + cruiseAltitude * 0.4);
    const climbPoint2 = startSurface
      .clone()
      .lerp(endSurface, 0.35)
      .normalize()
      .multiplyScalar(radius + cruiseAltitude * 0.75);
    const cruisePeak = startSurface
      .clone()
      .lerp(endSurface, 0.5)
      .normalize()
      .multiplyScalar(radius + cruiseAltitude * 0.85);
    const descentPoint1 = startSurface
      .clone()
      .lerp(endSurface, 0.65)
      .normalize()
      .multiplyScalar(radius + cruiseAltitude * 0.75);
    const descentPoint2 = startSurface
      .clone()
      .lerp(endSurface, 0.8)
      .normalize()
      .multiplyScalar(radius + cruiseAltitude * 0.4);

    const startNormal = startSurface.clone().normalize();
    let pathDirStart = endSurface.clone().sub(startSurface);
    if (pathDirStart.lengthSq() < 1e-6) {
      pathDirStart = new THREE.Vector3().randomDirection();
    }
    let tangentStart = pathDirStart
      .clone()
      .sub(startNormal.clone().multiplyScalar(pathDirStart.dot(startNormal)));
    if (tangentStart.lengthSq() < 1e-6) {
      tangentStart = new THREE.Vector3().crossVectors(
        startNormal,
        new THREE.Vector3(0, 1, 0),
      );
      if (tangentStart.lengthSq() < 1e-6) {
        tangentStart = new THREE.Vector3(1, 0, 0);
      }
    }
    tangentStart.normalize();
    const tangentDistance = radius * 0.08;
    const surfaceLength = startSurface.length();
    const startTangentPoint = startSurface
      .clone()
      .add(tangentStart.clone().multiplyScalar(tangentDistance))
      .normalize()
      .multiplyScalar(surfaceLength);

    const endNormal = endSurface.clone().normalize();
    let pathDirEnd = startSurface.clone().sub(endSurface);
    if (pathDirEnd.lengthSq() < 1e-6) {
      pathDirEnd = new THREE.Vector3().randomDirection();
    }
    let tangentEnd = pathDirEnd
      .clone()
      .sub(endNormal.clone().multiplyScalar(pathDirEnd.dot(endNormal)));
    if (tangentEnd.lengthSq() < 1e-6) {
      tangentEnd = new THREE.Vector3().crossVectors(
        endNormal,
        new THREE.Vector3(0, 1, 0),
      );
      if (tangentEnd.lengthSq() < 1e-6) {
        tangentEnd = new THREE.Vector3(1, 0, 0);
      }
    }
    tangentEnd.normalize();
    const endSurfaceLength = endSurface.length();
    const endTangentPoint = endSurface
      .clone()
      .add(tangentEnd.clone().multiplyScalar(tangentDistance))
      .normalize()
      .multiplyScalar(endSurfaceLength);

    const controlPoints = [
      startSurface,
      startTangentPoint,
      climbPoint1,
      climbPoint2,
      cruisePeak,
      descentPoint1,
      descentPoint2,
      endTangentPoint,
      endSurface,
    ];

    return this.ensureMinimumCurveAltitude(
      controlPoints,
      radius,
      minCurveAltitude,
    );
  }

  /**
   * Infer a sphere radius from legacy bounds configuration.
   * @param bounds - Legacy bounds configuration
   * @returns Inferred radius
   */
  static inferRadiusFromBounds(bounds?: Bounds): number {
    if (!bounds) {
      return 3000;
    }

    const maxX = Math.max(
      Math.abs(bounds.minX ?? 0),
      Math.abs(bounds.maxX ?? 0),
    );
    const maxY = Math.max(
      Math.abs(bounds.minY ?? 0),
      Math.abs(bounds.maxY ?? 0),
    );
    const maxZ = Math.max(
      Math.abs(bounds.minZ ?? 0),
      Math.abs(bounds.maxZ ?? 0),
    );

    return Math.sqrt(maxX * maxX + maxY * maxY + maxZ * maxZ);
  }

  /**
   * Infer the sphere center from legacy bounds configuration.
   * @param bounds - Legacy bounds configuration
   * @returns Inferred center point
   */
  static inferCenterFromBounds(bounds?: Bounds): THREE.Vector3 {
    if (!bounds) {
      return new THREE.Vector3();
    }

    return new THREE.Vector3(
      ((bounds.minX ?? 0) + (bounds.maxX ?? 0)) * 0.5,
      ((bounds.minY ?? 0) + (bounds.maxY ?? 0)) * 0.5,
      ((bounds.minZ ?? 0) + (bounds.maxZ ?? 0)) * 0.5,
    );
  }

  /**
   * Generate random control points for a smooth curve inside a sphere.
   * @param options - Configuration options
   * @returns Array of control points including start and end
   */
  static generateRandomCurve(
    options: RandomCurveOptions = {},
  ): THREE.Vector3[] {
    const center = options.center
      ? options.center.clone()
      : this.inferCenterFromBounds(options.bounds);

    const radius =
      options.radius !== undefined
        ? options.radius
        : this.inferRadiusFromBounds(options.bounds);

    const spread = Math.min(
      options.spread !== undefined ? options.spread : radius * 0.6,
      radius,
    );

    const start = options.start
      ? options.start.clone()
      : this.randomPointInSphere(radius).add(center);
    this.clampToSphere(start, radius, center);

    const end = options.end
      ? options.end.clone()
      : this.randomPointInSphere(radius).add(center);
    this.clampToSphere(end, radius, center);

    const numControlPoints =
      options.numControlPoints !== undefined
        ? options.numControlPoints
        : Math.floor(THREE.MathUtils.randFloat(2, 5));

    const controlPoints: THREE.Vector3[] = [start];

    for (let i = 1; i <= numControlPoints; i++) {
      const t = i / (numControlPoints + 1);
      const basePoint = new THREE.Vector3().lerpVectors(start, end, t);
      const offset = this.randomPointInSphere(spread);
      const controlPoint = basePoint.add(offset);

      this.clampToSphere(controlPoint, radius, center);
      controlPoints.push(controlPoint);
    }

    controlPoints.push(end);

    return controlPoints;
  }

  /**
   * Generate a random color
   * @param options - Color generation options
   * @returns Color as hex number
   */
  static generateRandomColor(options: ColorOptions = {}): number {
    const hue = Math.random();
    const saturation =
      options.saturation !== undefined
        ? options.saturation
        : THREE.MathUtils.randFloat(0.6, 1.0);
    const lightness =
      options.lightness !== undefined
        ? options.lightness
        : THREE.MathUtils.randFloat(0.4, 0.7);

    const color = new THREE.Color();
    color.setHSL(hue, saturation, lightness);

    return color.getHex();
  }

  /**
   * Generate flight configuration with random parameters
   * @param options - Configuration options
   * @returns Flight configuration object
   */
  static generateRandomFlightConfig(
    options: FlightConfigOptions = {},
  ): FlightConfig {
    const controlPoints = this.generateRandomCurve(options);

    return {
      controlPoints,
      segmentCount: options.segmentCount || 100,
      curveColor: options.curveColor || this.generateRandomColor(),
      paneCount: options.paneCount || 1,
      paneSize: options.paneSize || THREE.MathUtils.randFloat(80, 150),
      paneColor: options.paneColor || this.generateRandomColor(),
      animationSpeed:
        options.animationSpeed || THREE.MathUtils.randFloat(0.05, 0.15),
      tiltMode: options.tiltMode || "Perpendicular",
      returnFlight: options.returnFlight || false,
    };
  }

  /**
   * Plane entry utility functions
   */

  /**
   * Clone a plane entry object
   * @param entry - Plane entry to clone
   * @returns Cloned plane entry or null
   */
  static clonePlaneEntry(entry: PlaneEntry | null): PlaneEntry | null {
    if (!entry) return null;
    const { name, svg, color, atlasIndex } = entry;
    return { name, svg, color, atlasIndex };
  }

  /**
   * Get plane entry by atlas index
   * @param index - Atlas index
   * @param planeEntries - Array of plane entries
   * @returns Plane entry or null
   */
  static getPlaneEntryByAtlasIndex(
    index: number,
    planeEntries: PlaneEntry[],
  ): PlaneEntry | null {
    if (typeof index !== "number") return null;
    if (index < 0 || index >= planeEntries.length) return null;
    return planeEntries[index];
  }

  /**
   * Get plane entry by SVG name
   * @param svgName - SVG file name
   * @param planeEntries - Array of plane entries
   * @returns Plane entry or null
   */
  static getPlaneEntryBySvg(
    svgName: string,
    planeEntries: PlaneEntry[],
  ): PlaneEntry | null {
    if (typeof svgName !== "string" || !svgName) return null;
    return planeEntries.find((entry) => entry.svg === svgName) || null;
  }

  /**
   * Get plane entry by name
   * @param name - Plane name
   * @param planeEntries - Array of plane entries
   * @returns Plane entry or null
   */
  static getPlaneEntryByName(
    name: string,
    planeEntries: PlaneEntry[],
  ): PlaneEntry | null {
    if (typeof name !== "string" || !name) return null;
    return planeEntries.find((entry) => entry.name === name) || null;
  }

  /**
   * Get a random plane entry
   * @param planeEntries - Array of plane entries
   * @returns Random plane entry or null
   */
  static getRandomPlaneEntry(planeEntries: PlaneEntry[]): PlaneEntry | null {
    if (!planeEntries.length) return null;
    const randomIndex = Math.floor(Math.random() * planeEntries.length);
    return planeEntries[randomIndex];
  }

  /**
   * Ensure plane defaults are set in flight configuration
   * @param config - Partial flight configuration
   * @param planeEntries - Array of available plane entries
   * @param defaultPlaneColor - Default plane color
   * @param parseHexColor - Function to parse hex colors
   * @returns Complete flight configuration with plane defaults
   */
  static ensurePlaneDefaults(
    config: Partial<FlightConfig> = {},
    planeEntries: PlaneEntry[],
    defaultPlaneColor: number,
    parseHexColor: (value: any, fallback: number) => number,
  ): FlightConfig {
    const providedPlaneInfo = config.planeInfo;
    let planeEntry: PlaneEntry | null = null;

    if (providedPlaneInfo && typeof providedPlaneInfo === "object") {
      if (typeof providedPlaneInfo.atlasIndex === "number") {
        planeEntry = this.getPlaneEntryByAtlasIndex(
          providedPlaneInfo.atlasIndex,
          planeEntries,
        );
      }
      if (!planeEntry && providedPlaneInfo.svg) {
        planeEntry = this.getPlaneEntryBySvg(providedPlaneInfo.svg, planeEntries);
      }
      if (!planeEntry && providedPlaneInfo.name) {
        planeEntry = this.getPlaneEntryByName(providedPlaneInfo.name, planeEntries);
      }
    }

    if (!planeEntry && typeof config.paneTextureIndex === "number") {
      planeEntry = this.getPlaneEntryByAtlasIndex(
        config.paneTextureIndex,
        planeEntries,
      );
    }

    if (!planeEntry) {
      planeEntry = this.getRandomPlaneEntry(planeEntries);
    }

    if (!planeEntry) {
      const fallbackColor =
        typeof config.paneColor === "number"
          ? config.paneColor
          : defaultPlaneColor;
      const fallbackTextureIndex =
        typeof config.paneTextureIndex === "number" ? config.paneTextureIndex : 0;

      return {
        controlPoints: config.controlPoints || [],
        segmentCount: config.segmentCount || 100,
        paneSize: config.paneSize || 100,
        elevationOffset: config.elevationOffset || 15,
        animationSpeed: config.animationSpeed || 0.1,
        tiltMode: config.tiltMode || "Tangent",
        returnFlight: config.returnFlight || false,
        paneColor: fallbackColor,
        paneTextureIndex: fallbackTextureIndex,
        planeInfo: providedPlaneInfo ?? null,
        flightData: config.flightData || null,
      };
    }

    return {
      controlPoints: config.controlPoints || [],
      segmentCount: config.segmentCount || 100,
      paneSize: config.paneSize || 100,
      elevationOffset: config.elevationOffset || 15,
      animationSpeed: config.animationSpeed || 0.1,
      tiltMode: config.tiltMode || "Tangent",
      returnFlight: config.returnFlight || false,
      paneColor: parseHexColor(planeEntry.color, defaultPlaneColor),
      paneTextureIndex: planeEntry.atlasIndex,
      planeInfo: this.clonePlaneEntry(planeEntry),
      flightData: config.flightData || null,
    };
  }

  /**
   * Assign a random plane to flight configuration
   * @param config - Partial flight configuration
   * @param planeEntries - Array of available plane entries
   * @param defaultPlaneColor - Default plane color
   * @param parseHexColor - Function to parse hex colors
   * @returns Flight configuration with random plane assigned
   */
  static assignRandomPlane(
    config: Partial<FlightConfig> = {},
    planeEntries: PlaneEntry[],
    defaultPlaneColor: number,
    parseHexColor: (value: any, fallback: number) => number,
  ): FlightConfig {
    return this.ensurePlaneDefaults(
      {
        ...config,
        planeInfo: null,
        paneTextureIndex: undefined,
        paneColor: undefined,
      },
      planeEntries,
      defaultPlaneColor,
      parseHexColor,
    );
  }

  /**
   * Create flight configuration from flight data
   * @param entry - Flight data entry
   * @param params - GUI parameters
   * @param earthRadius - Earth radius
   * @param takeoffLandingOffset - Takeoff/landing offset
   * @param minCurveAltitude - Minimum curve altitude
   * @param minCruiseAltitude - Minimum cruise altitude
   * @param maxCruiseAltitude - Maximum cruise altitude
   * @param planeEntries - Array of available plane entries
   * @param defaultPlaneColor - Default plane color
   * @param parseHexColor - Function to parse hex colors
   * @returns Flight configuration or null
   */
  static createDataFlightConfig(
    entry: FlightData,
    params: any,
    earthRadius: number,
    takeoffLandingOffset: number,
    minCurveAltitude: number,
    minCruiseAltitude: number,
    maxCruiseAltitude: number,
    planeEntries: PlaneEntry[],
    defaultPlaneColor: number,
    parseHexColor: (value: any, fallback: number) => number,
  ): FlightConfig | null {
    if (!entry) {
      return null;
    }

    const { departure, arrival } = entry;
    const controlPoints = this.generateParabolicControlPoints(
      departure,
      arrival,
      {
        radius: earthRadius,
        takeoffOffset: takeoffLandingOffset,
        minCurveAltitude: minCurveAltitude,
        minCruiseAltitude: minCruiseAltitude,
        maxCruiseAltitude: maxCruiseAltitude,
      },
    );
    if (!controlPoints.length) {
      return null;
    }

    return this.assignRandomPlane(
      {
        controlPoints,
        segmentCount: params.segmentCount,
        curveColor: this.createGradientColorConfig(departure),
        paneCount: 1,
        paneSize: params.planeSize,
        elevationOffset: params.elevationOffset,
        animationSpeed: params.animationSpeed,
        tiltMode: params.tiltMode,
        returnFlight: params.returnFlight,
        flightData: {
          departure,
          arrival,
        },
      },
      planeEntries,
      defaultPlaneColor,
      parseHexColor,
    );
  }

  // Note: createFlightFromConfig moved back to main.ts due to complex type dependencies

  /**
   * Pre-generate flight configurations for stability
   * @param dataFlights - Array of flight data
   * @param maxFlights - Maximum number of flights
   * @param params - GUI parameters
   * @param earthRadius - Earth radius
   * @param minCurveAltitude - Minimum curve altitude
   * @param planeEntries - Array of plane entries
   * @param defaultPlaneColor - Default plane color
   * @param parseHexColor - Function to parse hex colors
   * @param createDataFlightConfigFn - Function to create data flight config
   * @param assignRandomPlaneFn - Function to assign random plane
   * @returns Array of pre-generated flight configurations
   */
  static preGenerateFlightConfigs(
    dataFlights: FlightData[],
    maxFlights: number,
    params: any,
    earthRadius: number,
    minCurveAltitude: number,
    planeEntries: PlaneEntry[],
    defaultPlaneColor: number,
    parseHexColor: (value: any, fallback: number) => number,
    createDataFlightConfigFn: (entry: FlightData) => FlightConfig | null,
    assignRandomPlaneFn: (config: Partial<FlightConfig>) => FlightConfig,
  ): FlightConfig[] {
    const preGeneratedConfigs: FlightConfig[] = [];

    if (Array.isArray(dataFlights) && dataFlights.length > 0) {
      dataFlights.forEach((flightEntry) => {
        const config = createDataFlightConfigFn(flightEntry);
        if (!config) {
          return;
        }

        const configWithPlane = this.ensurePlaneDefaults(
          config,
          planeEntries,
          defaultPlaneColor,
          parseHexColor,
        );
        const normalizedPoints = this.normalizeControlPoints(
          configWithPlane.controlPoints,
          earthRadius,
          minCurveAltitude,
        );

        preGeneratedConfigs.push({
          ...configWithPlane,
          controlPoints: normalizedPoints,
          elevationOffset:
            configWithPlane.elevationOffset !== undefined
              ? configWithPlane.elevationOffset
              : params.elevationOffset,
          paneTextureIndex: configWithPlane.paneTextureIndex,
          paneColor: configWithPlane.paneColor,
          planeInfo: configWithPlane.planeInfo,
          _randomSpeed:
            typeof configWithPlane.animationSpeed === "number"
              ? configWithPlane.animationSpeed
              : undefined,
          returnFlight: params.returnFlight,
        });
      });

      return preGeneratedConfigs;
    }

    for (let i = 0; i < maxFlights; i++) {
      let config = this.generateRandomFlightConfig({
        segmentCount: params.segmentCount,
        tiltMode: params.tiltMode,
        numControlPoints: 2,
      });
      config = assignRandomPlaneFn({
        ...config,
        elevationOffset: params.elevationOffset,
        flightData: null,
      });
      const normalizedPoints = this.normalizeControlPoints(
        config.controlPoints,
        earthRadius,
        minCurveAltitude,
      );
      preGeneratedConfigs.push({
        ...config,
        controlPoints: normalizedPoints,
        elevationOffset: config.elevationOffset,
        paneTextureIndex: config.paneTextureIndex,
        paneColor: config.paneColor,
        planeInfo: config.planeInfo,
        _randomSpeed:
          typeof config.animationSpeed === "number"
            ? config.animationSpeed
            : undefined,
        returnFlight: params.returnFlight,
        flightData: null,
      });
    }

    return preGeneratedConfigs;
  }

  /**
   * Randomize all flight curves
   * @param flights - Array of existing flights
   * @param preGeneratedConfigs - Array of pre-generated configs (will be modified)
   * @param params - GUI parameters
   * @param earthRadius - Earth radius
   * @param minCurveAltitude - Minimum curve altitude
   * @param assignRandomPlaneFn - Function to assign random plane
   * @param resolvePaneColorFn - Function to resolve pane color
   * @param resolveAnimationSpeedFn - Function to resolve animation speed
   * @param mergedCurves - Merged curves renderer
   */
  static randomizeAllFlightCurves(
    flights: Flight[],
    preGeneratedConfigs: FlightConfig[],
    params: any,
    earthRadius: number,
    minCurveAltitude: number,
    assignRandomPlaneFn: (config: Partial<FlightConfig>) => FlightConfig,
    resolvePaneColorFn: (config: Partial<FlightConfig>) => number,
    resolveAnimationSpeedFn: (config: Record<string, any>) => number,
    mergedCurves: Curves | null,
  ): void {
    flights.forEach((flight, index) => {
      const randomConfig = this.generateRandomFlightConfig({
        numControlPoints: 2,
      });
      const normalizedPoints = this.normalizeControlPoints(
        randomConfig.controlPoints,
        earthRadius,
        minCurveAltitude,
      );

      const existingConfig = preGeneratedConfigs[index] || {};
      let updatedConfig: FlightConfig = {
        ...existingConfig,
        ...randomConfig,
        controlPoints: normalizedPoints,
        segmentCount: params.segmentCount,
        curveColor: randomConfig.curveColor,
        elevationOffset:
          (existingConfig as any).elevationOffset !== undefined
            ? (existingConfig as any).elevationOffset
            : params.elevationOffset,
        flightData: (existingConfig as any).flightData ?? null,
        planeInfo: null,
        paneTextureIndex: undefined,
        paneColor: undefined,
      };
      updatedConfig = assignRandomPlaneFn(updatedConfig);
      updatedConfig._randomSpeed = params.randomSpeed
        ? randomConfig.animationSpeed
        : undefined;
      updatedConfig.returnFlight = params.returnFlight;
      preGeneratedConfigs[index] = updatedConfig;

      flight.setFlightData(updatedConfig.flightData);
      flight.setControlPoints(this.cloneControlPoints(normalizedPoints));
      flight.setPaneElevation(updatedConfig.elevationOffset);
      flight.setPaneTextureIndex(updatedConfig.paneTextureIndex);
      flight.setCurveColor(updatedConfig.curveColor);
      const paneColor = resolvePaneColorFn(updatedConfig);
      flight.setPaneColor(paneColor);
      const speed = resolveAnimationSpeedFn(updatedConfig);
      flight.setAnimationSpeed(speed);
      flight.setReturnFlight(params.returnFlight);
    });

    if (mergedCurves) {
      mergedCurves.applyUpdates();
    }
  }
}
