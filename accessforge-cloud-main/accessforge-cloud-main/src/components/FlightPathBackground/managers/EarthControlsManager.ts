import * as THREE from "three";
import type { Earth } from "../space/Earth.ts";
import type { EarthControlsOptions } from "../common/Types.js";

export class EarthControlsManager {
  private ambientLight: THREE.AmbientLight;
  private directionalLight: THREE.DirectionalLight;
  private getGuiControls: () => any;
  private updateLighting: () => void;
  private getEarth: () => Earth | null;
  private getCurrentUtcTimeHours: () => number;
  private hoursToTimeString: (hours: number) => string;
  private baseAmbientColor: THREE.Color | null;
  private baseAmbientIntensity: number;
  private baseDirectionalIntensity: number;
  private dayBrightnessPercent: number;
  private nightBrightnessPercent: number;
  private simulatedTime: number;
  private timeDisplay: string;
  private realTimeSunEnabled: boolean;
  private readonly DEFAULT_DAY_PERCENT = 70;
  private readonly DEFAULT_NIGHT_PERCENT = 40;

  constructor(options: EarthControlsOptions) {
    this.ambientLight = options.ambientLight;
    this.directionalLight = options.directionalLight;
    this.getGuiControls = options.getGuiControls;
    this.updateLighting = options.updateLighting;
    this.getEarth = options.getEarth;
    this.getCurrentUtcTimeHours = options.getCurrentUtcTimeHours;
    this.hoursToTimeString = options.hoursToTimeString;

    this.baseAmbientColor = this.ambientLight.color.clone();
    this.baseAmbientIntensity = this.ambientLight.intensity;
    this.baseDirectionalIntensity = this.directionalLight.intensity;
    this.dayBrightnessPercent = this.DEFAULT_DAY_PERCENT;
    this.nightBrightnessPercent = this.DEFAULT_NIGHT_PERCENT;
    this.simulatedTime = this.getCurrentUtcTimeHours();
    this.timeDisplay = this.hoursToTimeString(this.simulatedTime);
    this.realTimeSunEnabled = true;
  }

  public toggleDayNightEffect(enabled: boolean): void {
    if (enabled) {
      this.directionalLight.visible = true;
      this.ambientLight.color.copy(this.baseAmbientColor);
      this.ambientLight.intensity = this.baseAmbientIntensity;
      this.directionalLight.intensity = this.baseDirectionalIntensity;
    } else {
      this.directionalLight.visible = false;
      this.directionalLight.intensity = 0;
    }

    const guiControls = this.getGuiControls();
    if (guiControls) {
      guiControls.dayNightEffect = enabled;
    }

    this.updateLighting();
  }

  public toggleAtmosphereEffect(enabled: boolean): void {
    const earth = this.getEarth();
    const atmosphereMesh = earth?.atmosphere?.mesh;
    if (atmosphereMesh) {
      atmosphereMesh.visible = enabled;
    }

    const guiControls = this.getGuiControls();
    if (guiControls) {
      guiControls.atmosphereEffect = enabled;
    }
  }

  public getBaseAmbientColor(): THREE.Color {
    return this.baseAmbientColor;
  }

  public getBaseAmbientIntensity(): number {
    return this.baseAmbientIntensity;
  }

  public getDayBrightnessPercent(): number {
    return this.dayBrightnessPercent;
  }

  public getNightBrightnessPercent(): number {
    return this.nightBrightnessPercent;
  }

  public setDayBrightness(percent: number): void {
    const clamped = this.clampBrightness(percent, this.DEFAULT_DAY_PERCENT);
    if (this.dayBrightnessPercent === clamped) {
      return;
    }
    this.dayBrightnessPercent = clamped;

    const guiControls = this.getGuiControls();
    if (guiControls && guiControls.dayBrightness !== clamped) {
      guiControls.dayBrightness = clamped;
    }

    this.updateLighting();
  }

  public setNightBrightness(percent: number): void {
    const clamped = this.clampBrightness(percent, this.DEFAULT_NIGHT_PERCENT);
    if (this.nightBrightnessPercent === clamped) {
      return;
    }
    this.nightBrightnessPercent = clamped;

    const guiControls = this.getGuiControls();
    if (guiControls && guiControls.nightBrightness !== clamped) {
      guiControls.nightBrightness = clamped;
    }

    this.updateLighting();
  }

  public enableRealTimeSun(): void {
    this.realTimeSunEnabled = true;
    this.updateSimulatedTime(this.getCurrentUtcTimeHours(), {
      disableRealTime: false,
    });
  }

  public disableRealTimeSun(): void {
    if (!this.realTimeSunEnabled) return;
    this.realTimeSunEnabled = false;
    this.syncGui();
  }

  public initializeFromGui(gui: any): void {
    if (!gui) return;

    this.dayBrightnessPercent = this.clampBrightness(
      gui.dayBrightness,
      this.DEFAULT_DAY_PERCENT,
    );
    this.nightBrightnessPercent = this.clampBrightness(
      gui.nightBrightness,
      this.DEFAULT_NIGHT_PERCENT,
    );

    const initialTime = this.clampTime(gui.simulatedTime);
    this.simulatedTime = initialTime;
    this.timeDisplay =
      typeof gui.timeDisplay === "string"
        ? gui.timeDisplay
        : this.hoursToTimeString(initialTime);
    this.realTimeSunEnabled = Boolean(gui.realTimeSun);

    this.syncGui();
  }

  public getSimulatedTime(): number {
    if (this.realTimeSunEnabled) {
      this.updateSimulatedTime(this.getCurrentUtcTimeHours(), {
        disableRealTime: false,
      });
    }
    return this.simulatedTime;
  }

  public getTimeDisplay(): string {
    return this.timeDisplay;
  }

  public isRealTimeSunEnabled(): boolean {
    return this.realTimeSunEnabled;
  }

  public setSimulatedTime(hours: number): void {
    this.updateSimulatedTime(hours, { disableRealTime: true });
  }

  public setTimeDisplay(value: string): boolean {
    if (typeof value !== "string") {
      return false;
    }
    const parsed = this.parseTimeString(value);
    if (!Number.isFinite(parsed)) {
      return false;
    }
    this.updateSimulatedTime(parsed, { disableRealTime: true });
    return true;
  }

  private clampBrightness(value: any, fallback: number): number {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return fallback;
    }
    return THREE.MathUtils.clamp(numeric, 0, 100);
  }

  private clampTime(value: any): number {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    return THREE.MathUtils.clamp(numeric, 0, 24);
  }

  private updateSimulatedTime(
    hours: number,
    options: { disableRealTime?: boolean } = {},
  ): void {
    const clamped = this.clampTime(hours);
    this.simulatedTime = clamped;
    this.timeDisplay = this.hoursToTimeString(clamped);
    if (options.disableRealTime) {
      this.realTimeSunEnabled = false;
    }
    this.syncGui();
  }

  private parseTimeString(value: string): number {
    const parts = value.split(":").map(Number);
    if (parts.some((part) => Number.isNaN(part))) {
      return NaN;
    }
    const hours = parts[0] || 0;
    const minutes = parts[1] || 0;
    const seconds = parts[2] || 0;
    return hours + minutes / 60 + seconds / 3600;
  }

  private syncGui(): void {
    const guiControls = this.getGuiControls();
    if (!guiControls) return;

    if (guiControls.dayBrightness !== this.dayBrightnessPercent) {
      guiControls.dayBrightness = this.dayBrightnessPercent;
    }
    if (guiControls.nightBrightness !== this.nightBrightnessPercent) {
      guiControls.nightBrightness = this.nightBrightnessPercent;
    }
    if (guiControls.simulatedTime !== this.simulatedTime) {
      guiControls.simulatedTime = this.simulatedTime;
    }
    if (guiControls.timeDisplay !== this.timeDisplay) {
      guiControls.timeDisplay = this.timeDisplay;
    }
    if (guiControls.realTimeSun !== this.realTimeSunEnabled) {
      guiControls.realTimeSun = this.realTimeSunEnabled;
    }
  }
}
