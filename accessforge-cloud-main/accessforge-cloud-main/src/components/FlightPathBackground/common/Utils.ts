import * as THREE from "three";

/**
 * Utility functions for mathematical and geometric operations
 */

/**
 * Convert latitude/longitude coordinates to 3D Vector3 position
 * @param lat - Latitude (-90 to +90, south to north)
 * @param lng - Longitude (-180 to +180, west to east)
 * @param radius - Sphere radius
 * @returns 3D position vector
 */
export function latLngToVector3(
  lat: number,
  lng: number,
  radius: number,
): THREE.Vector3 {
  // Convert lat/lng to spherical coordinates
  const phi = ((90 - lat) * Math.PI) / 180; // Latitude: 0 at north pole, PI at south pole
  const theta = ((-lng + 180) * Math.PI) / 180; // Longitude: direct conversion

  // Standard spherical to cartesian conversion
  const x = radius * Math.sin(phi) * Math.cos(theta);
  const y = radius * Math.cos(phi);
  const z = radius * Math.sin(phi) * Math.sin(theta);

  // Apply coordinate system transformation to match our rotated globe:
  // - Globe is rotated -90° around Y-axis
  // - This means we need to rotate coordinates +90° to compensate
  // Rotation matrix for +90° around Y-axis: [cos(90) 0 sin(90); 0 1 0; -sin(90) 0 cos(90)]
  // Which simplifies to: [0 0 1; 0 1 0; -1 0 0]

  const rotatedX = z; // X becomes Z
  const rotatedY = y; // Y stays Y
  const rotatedZ = -x; // Z becomes -X

  return new THREE.Vector3(rotatedX, rotatedY, rotatedZ);
}

/**
 * Generate a random point on the surface of a sphere
 * @param radius - Sphere radius
 * @returns Random 3D position on sphere surface
 */
export function getRandomPointOnSphere(radius: number): THREE.Vector3 {
  const phi = Math.random() * Math.PI * 2;
  const theta = Math.random() * Math.PI;
  const x = radius * Math.sin(theta) * Math.cos(phi);
  const y = radius * Math.sin(theta) * Math.sin(phi);
  const z = radius * Math.cos(theta);
  return new THREE.Vector3(x, y, z);
}

/**
 * Convert degrees to radians
 * @param degrees - Angle in degrees
 * @returns Angle in radians
 */
export function degreesToRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/**
 * Convert radians to degrees
 * @param radians - Angle in radians
 * @returns Angle in degrees
 */
export function radiansToDegrees(radians: number): number {
  return (radians * 180) / Math.PI;
}

/**
 * Clamp a value between min and max
 * @param value - Value to clamp
 * @param min - Minimum value
 * @param max - Maximum value
 * @returns Clamped value
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/**
 * Interface for sun position coordinates
 */
export interface SunPosition {
  lat: number;
  lng: number;
}

/**
 * Calculate the sun's position based on current UTC time or simulated time
 * Returns the subsolar point (latitude/longitude where sun is directly overhead)
 * @param simulatedTimeHours - Optional simulated time in UTC hours (0-24)
 * @returns Object with lat, lng properties
 */
export function getSunPosition(
  simulatedTimeHours: number | null = null,
): SunPosition {
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const utcDate = new Date(utc);

  // Calculate day of year (1-365/366)
  const start = new Date(utcDate.getFullYear(), 0, 1); // Start from Jan 1st
  const diff = utcDate.getTime() - start.getTime();
  const dayOfYear = Math.floor(diff / (1000 * 60 * 60 * 24)) + 1;

  // Solar declination (latitude where sun is directly overhead)
  // More accurate formula using day of year
  // October 1st is around day 274, which should give ~-3.25° declination
  const declination =
    23.45 * Math.sin(degreesToRadians((360 / 365.25) * (dayOfYear - 81)));

  // Use simulated time if provided, otherwise use current time
  let timeDecimal: number;
  if (simulatedTimeHours !== null) {
    timeDecimal = simulatedTimeHours;
  } else {
    const hours = utcDate.getUTCHours();
    const minutes = utcDate.getUTCMinutes();
    const seconds = utcDate.getUTCSeconds();
    timeDecimal = hours + minutes / 60 + seconds / 3600;
  }

  // Calculate longitude where sun is at zenith
  // At 02:34:43 UTC (2.578 hours), sun should be at 138.75° East
  // Solar longitude = (12 - UTC_time) * 15
  const longitude = (12 - timeDecimal) * 15;

  // Normalize to -180 to +180 range
  let normalizedLongitude = longitude;
  while (normalizedLongitude > 180) normalizedLongitude -= 360;
  while (normalizedLongitude < -180) normalizedLongitude += 360;

  return {
    lat: declination,
    lng: normalizedLongitude,
  };
}

/**
 * Convert sun position to 3D vector for directional light
 * @param radius - Earth radius
 * @param simulatedTimeHours - Optional simulated time in UTC hours (0-24)
 * @returns Sun position vector
 */
export function getSunVector3(
  radius: number = 3000,
  simulatedTimeHours: number | null = null,
): THREE.Vector3 {
  const sunPos = getSunPosition(simulatedTimeHours);
  const sunVector = latLngToVector3(sunPos.lat, sunPos.lng, radius * 3); // Place sun far from Earth
  return sunVector;
}

/**
 * Time utility functions
 */

/**
 * Get current Pacific time in decimal hours (0-24)
 * @returns Current Pacific time in decimal hours
 */
export function getCurrentPacificTimeHours(): number {
  const now = new Date();
  const pacificTime = new Date(
    now.toLocaleString("en-US", { timeZone: "America/Los_Angeles" }),
  );
  return pacificTime.getHours() + pacificTime.getMinutes() / 60;
}

/**
 * Get current UTC time in decimal hours (0-24)
 * @returns Current UTC time in decimal hours
 */
export function getCurrentUtcTimeHours(): number {
  const now = new Date();
  const hours = now.getUTCHours();
  const minutes = now.getUTCMinutes();
  const seconds = now.getUTCSeconds();
  return hours + minutes / 60 + seconds / 3600;
}

/**
 * Convert decimal hours to HH:MM:SS format
 * @param hours - Decimal hours (0-24)
 * @returns Time in HH:MM:SS format
 */
export function hoursToTimeString(hours: number): string {
  const h = Math.floor(hours);
  const remainingMinutes = (hours - h) * 60;
  const m = Math.floor(remainingMinutes);
  const s = Math.floor((remainingMinutes - m) * 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

/**
 * Convert HH:MM or HH:MM:SS format to decimal hours
 * @param timeString - Time in HH:MM or HH:MM:SS format
 * @returns Decimal hours
 */
export function timeStringToHours(timeString: string): number {
  const parts = timeString.split(":").map(Number);
  const hours = parts[0] || 0;
  const minutes = parts[1] || 0;
  const seconds = parts[2] || 0;
  return hours + minutes / 60 + seconds / 3600;
}

/**
 * Animate camera from current position to target position with smooth easing
 * @param camera - The camera to animate
 * @param startPosition - Starting camera position
 * @param targetPosition - Target camera position
 * @param duration - Animation duration in milliseconds
 * @param delay - Delay before starting animation in milliseconds
 */
export function animateCameraToPosition(
  camera: THREE.Camera,
  startPosition: THREE.Vector3,
  targetPosition: THREE.Vector3,
  duration: number = 2000,
  delay: number = 0,
): void {
  const animateCamera = () => {
    const startTime = Date.now();

    function animate() {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Use easing function for smooth animation (ease-out cubic)
      const easeProgress = 1 - Math.pow(1 - progress, 3);

      // Interpolate position
      camera.position.lerpVectors(startPosition, targetPosition, easeProgress);
      camera.lookAt(0, 0, 0); // Look at Earth center

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    }

    animate();
  };

  if (delay > 0) {
    setTimeout(animateCamera, delay);
  } else {
    animateCamera();
  }
}

/**
 * Interface for latitude/longitude coordinates
 */
export interface LatLng {
  lat: number;
  lng: number;
}

/**
 * Convert 3D Vector3 position back to latitude/longitude coordinates
 * @param position - 3D position vector
 * @param radius - Sphere radius used for the conversion
 * @returns Object with lat, lng properties
 */
export function vector3ToLatLng(
  position: THREE.Vector3,
  radius: number,
): LatLng {
  // Reverse the coordinate transformation applied in latLngToVector3
  // Original transformation: rotatedX = z, rotatedY = y, rotatedZ = -x
  // So to reverse: x = -rotatedZ, y = rotatedY, z = rotatedX
  const x = -position.z;
  const y = position.y;
  const z = position.x;

  // Normalize the vector to the sphere surface
  const normalizedPosition = new THREE.Vector3(x, y, z)
    .normalize()
    .multiplyScalar(radius);

  // Convert cartesian back to spherical coordinates
  const phi = Math.acos(clamp(normalizedPosition.y / radius, -1, 1)); // Latitude angle
  const theta = Math.atan2(normalizedPosition.z, normalizedPosition.x); // Longitude angle

  // Convert to lat/lng degrees
  const lat = 90 - (phi * 180) / Math.PI; // 0 at north pole, 180 at south pole -> -90 to +90
  const lng = (((theta * 180) / Math.PI + 180) % 360) - 180; // -180 to +180

  return { lat, lng };
}

/**
 * Color and value utility functions
 */

/**
 * Parse a hex color value from various input types
 * @param colorValue - Color value to parse (number, string, etc.)
 * @param fallback - Fallback color if parsing fails
 * @returns Parsed color as number
 */
export function parseHexColor(
  colorValue: any,
  fallback: number = 0xff6666,
): number {
  if (typeof colorValue === "number" && Number.isFinite(colorValue)) {
    return colorValue;
  }
  if (typeof colorValue === "string") {
    const normalized = colorValue.trim().replace(/^#/, "");
    if (normalized.length > 0) {
      const parsed = parseInt(normalized, 16);
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
  }
  return fallback;
}

/**
 * Clamp a percentage value between 0 and 100
 * @param value - Value to clamp
 * @param fallbackPercent - Fallback percentage if value is invalid
 * @returns Clamped percentage value
 */
export function clampPercentValue(value: any, fallbackPercent: number): number {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallbackPercent;
  }
  return THREE.MathUtils.clamp(numeric, 0, 100);
}

/**
 * Resolve day intensity from percentage value
 * @param percentValue - Percentage value (0-100)
 * @param fallbackPercent - Fallback percentage if value is invalid
 * @returns Day intensity value (0.1 to 3.0)
 */
export function resolveDayIntensityFromPercent(
  percentValue: any,
  fallbackPercent: number = 70,
): number {
  const percent = clampPercentValue(percentValue, fallbackPercent) / 100;
  return THREE.MathUtils.lerp(0.1, 3.0, percent);
}

/**
 * Resolve night mix from percentage value
 * @param percentValue - Percentage value (0-100)
 * @param fallbackPercent - Fallback percentage if value is invalid
 * @returns Night mix value (0.0 to 1.0)
 */
export function resolveNightMixFromPercent(
  percentValue: any,
  fallbackPercent: number = 40,
): number {
  return clampPercentValue(percentValue, fallbackPercent) / 100;
}

/**
 * Lighting and rendering utility functions
 */

/**
 * Update lighting based on day/night settings
 * @param guiControls - GUI controls object
 * @param earthControlsManager - Earth controls manager
 * @param ambientLight - Ambient light object
 * @param directionalLight - Directional light object
 * @param targetAmbientColor - Target ambient color
 * @param defaultDayBrightness - Default day brightness percentage
 * @param defaultNightBrightness - Default night brightness percentage
 */
export function updateLighting(
  guiControls: any,
  earthControlsManager: any,
  ambientLight: THREE.AmbientLight,
  directionalLight: THREE.DirectionalLight,
  targetAmbientColor: THREE.Color,
  defaultDayBrightness: number = 70,
  defaultNightBrightness: number = 40,
): void {
  if (!guiControls) return;

  if (!guiControls.dayNightEffect) {
    ambientLight.color.copy(targetAmbientColor);
    ambientLight.intensity = 1.6;
    return;
  }

  const dayPercent = earthControlsManager
    ? earthControlsManager.getDayBrightnessPercent()
    : guiControls.dayBrightness ?? defaultDayBrightness;
  const nightPercent = earthControlsManager
    ? earthControlsManager.getNightBrightnessPercent()
    : guiControls.nightBrightness ?? defaultNightBrightness;

  const dayIntensity = resolveDayIntensityFromPercent(dayPercent);
  const nightMix = resolveNightMixFromPercent(nightPercent);

  directionalLight.intensity = dayIntensity;

  const baseIntensity = earthControlsManager
    ? earthControlsManager.getBaseAmbientIntensity()
    : ambientLight.intensity;
  const baseColor = earthControlsManager
    ? earthControlsManager.getBaseAmbientColor().clone()
    : ambientLight.color.clone();
  const targetAmbient = THREE.MathUtils.lerp(
    baseIntensity,
    dayIntensity * 0.95,
    nightMix,
  );
  const colorBlend = THREE.MathUtils.clamp(nightMix * 0.85, 0, 1);

  const blendedColor = baseColor.lerp(targetAmbientColor, colorBlend);
  ambientLight.color.copy(blendedColor);
  ambientLight.intensity = targetAmbient;
}

/**
 * Update sun position based on time
 * @param directionalLight - Directional light object
 * @param earth - Earth object
 * @param earthControlsManager - Earth controls manager
 * @param guiControls - GUI controls object
 * @param uiManager - UI manager for coordinate display
 * @param camera - Camera object
 * @param updateLightingFn - Function to update lighting
 */
export function updateSunPosition(
  directionalLight: THREE.DirectionalLight,
  earth: any,
  earthControlsManager: any,
  guiControls: any,
  uiManager: any,
  camera: THREE.Camera,
  updateLightingFn: () => void,
): void {
  if (!directionalLight) return;

  const radius = earth ? earth.getRadius() : 3000;

  const simulatedTime = earthControlsManager
    ? earthControlsManager.getSimulatedTime()
    : guiControls?.simulatedTime ?? getCurrentUtcTimeHours();

  if (guiControls) {
    guiControls.simulatedTime = simulatedTime;
    guiControls.timeDisplay = earthControlsManager
      ? earthControlsManager.getTimeDisplay()
      : hoursToTimeString(simulatedTime);
    guiControls.realTimeSun = earthControlsManager
      ? earthControlsManager.isRealTimeSunEnabled()
      : guiControls.realTimeSun;
  }

  const dayNightActive = guiControls ? guiControls.dayNightEffect : true;
  if (dayNightActive) {
    const sunVector = getSunVector3(radius, simulatedTime);
    directionalLight.position.copy(sunVector);
  }

  updateLightingFn();
  directionalLight.lookAt(0, 0, 0);
  uiManager.updateCoordinateDisplay(camera, earth);
}

/**
 * Set initial camera position relative to sun
 * @param earth - Earth object
 * @param camera - Camera object
 * @param uiManager - UI manager
 * @param initialCameraPositioned - Flag to track if camera was positioned
 * @returns Updated initialCameraPositioned flag
 */
export function setInitialCameraPosition(
  earth: any,
  camera: THREE.Camera,
  uiManager: any,
  initialCameraPositioned: boolean,
): boolean {
  if (!earth || initialCameraPositioned) return initialCameraPositioned;

  const radius = earth.getRadius();
  const sunPos = getSunVector3(radius, getCurrentUtcTimeHours());
  const sunDirection = sunPos.clone().normalize();

  const angle = THREE.MathUtils.degToRad(70);
  const rotatedDirection = new THREE.Vector3(
    sunDirection.x * Math.cos(angle) + sunDirection.z * Math.sin(angle),
    sunDirection.y,
    -sunDirection.x * Math.sin(angle) + sunDirection.z * Math.cos(angle),
  );

  const targetDistance = radius * 2.1;
  const targetPosition = rotatedDirection.multiplyScalar(targetDistance);
  const startPosition = targetPosition.clone().multiplyScalar(1.25);

  camera.position.copy(startPosition);
  camera.lookAt(0, 0, 0);
  animateCameraToPosition(camera, startPosition, targetPosition, 3000, 500);

  uiManager.removeLoadingScreen();
  return true;
}
