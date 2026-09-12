import { useState } from "react";
import { ChevronRight, ClipboardPaste, Copy, RotateCcw } from "lucide-react";
import {
  RENDER_STUDIO,
  SCENE_QUALITY_PRESETS
} from "cadgen-js/common/sceneSettings.js";
import { ENVIRONMENT_PRESETS } from "cadgen-js/lib/themeSettings";
import { copyTextToClipboard } from "@/ui/clipboard";
import { cn } from "@/ui/utils";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import { Button } from "../ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "../ui/collapsible";
import { Slider } from "../ui/slider";
import { Textarea } from "../ui/textarea";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorRow,
  FileSheetField,
  FileSheetFieldGrid,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet";

const STUDIO_OPTIONS = Object.freeze([
  { value: RENDER_STUDIO.LIGHT, label: "Light studio" },
  { value: RENDER_STUDIO.DARK, label: "Dark studio" }
]);

const BACKGROUND_OPTIONS = Object.freeze([
  { value: "solid", label: "Solid" },
  { value: "linear", label: "Linear" },
  { value: "radial", label: "Radial" },
  { value: "transparent", label: "Transparent" }
]);

const LIGHT_OPTIONS = Object.freeze([
  { value: "directional", label: "Key" },
  { value: "fill", label: "Fill" },
  { value: "rim", label: "Rim" },
  { value: "spot", label: "Spot" },
  { value: "point", label: "Point" }
]);

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

function RenderSlider({ label, value, min, max, step = 0.01, unit = "", digits = 2, onChange }) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
  const displayValue = `${formatNumber(numericValue, digits)}${unit}`;
  return (
    <FileSheetSliderField
      label={label}
      value={displayValue}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, {
        fallback: numericValue,
        min,
        max
      }))}
      valueInputProps={{ ariaLabel: `${label} value` }}
    >
      <Slider
        value={[numericValue]}
        min={min}
        max={max}
        step={step}
        onValueChange={(next) => onChange(clamp(Number(next[0]), min, max))}
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
      />
    </FileSheetSliderField>
  );
}

function PositionFields({ value = {}, onChange }) {
  return (
    <FileSheetFieldGrid columns={3}>
      {["x", "y", "z"].map((axis) => (
        <FileSheetField key={axis} label={axis.toUpperCase()}>
          <input
            type="number"
            min={-5000}
            max={5000}
            step="any"
            value={Number(value?.[axis]) || 0}
            onChange={(event) => onChange(axis, clamp(Number(event.target.value) || 0, -5000, 5000))}
            aria-label={`${axis.toUpperCase()} light position`}
            className="h-7 w-full rounded-md border border-input bg-transparent px-2 text-right text-[11px] tabular-nums outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
          />
        </FileSheetField>
      ))}
    </FileSheetFieldGrid>
  );
}

function DebugSettings({ payload, onCopyPayload, onApplyPayload }) {
  const [open, setOpen] = useState(false);
  const [manualPaste, setManualPaste] = useState(false);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");

  const applyText = async (text) => {
    try {
      await onApplyPayload?.(text);
      setStatus("Settings applied.");
      setManualPaste(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Render settings could not be applied.");
      setManualPaste(true);
      setDraft(String(text || ""));
    }
  };

  const pasteFromClipboard = async () => {
    setStatus("");
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.readText) {
        throw new Error("Clipboard reading is unavailable. Paste JSON below.");
      }
      const text = await navigator.clipboard.readText();
      setDraft(text);
      await applyText(text);
    } catch (error) {
      setManualPaste(true);
      setStatus(error instanceof Error ? error.message : "Clipboard reading is unavailable. Paste JSON below.");
    }
  };

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-3">
      <FileSheetButtonRow columns={1}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className={cn(FILE_SHEET_COMPACT_BUTTON_CLASSES, "justify-between")}
            aria-label={open ? "Collapse Debug" : "Expand Debug"}
          >
            Debug
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden="true" />
          </Button>
        </CollapsibleTrigger>
      </FileSheetButtonRow>
      <CollapsibleContent className="space-y-3">
          <FileSheetButtonRow columns={2}>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
              onClick={async () => {
                try {
                  await copyTextToClipboard(JSON.stringify(onCopyPayload?.() || payload, null, 2));
                  setStatus("Settings copied.");
                } catch (error) {
                  setStatus(error instanceof Error ? error.message : "Settings could not be copied.");
                }
              }}
            >
              <Copy className="size-3.5" aria-hidden="true" />
              Copy settings
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
              onClick={() => { void pasteFromClipboard(); }}
            >
              <ClipboardPaste className="size-3.5" aria-hidden="true" />
              Paste settings
            </Button>
          </FileSheetButtonRow>
          {manualPaste ? (
            <div className="space-y-2 px-2">
              <Textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                aria-label="Render settings JSON"
                placeholder="Paste render JSON"
                className="min-h-28 resize-y font-mono text-[10px]"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={cn(FILE_SHEET_COMPACT_BUTTON_CLASSES, "w-full justify-center")}
                onClick={() => { void applyText(draft); }}
              >
                Apply JSON
              </Button>
            </div>
          ) : null}
          {status ? <FileSheetStatusText tone={status.includes("applied") || status.includes("copied") ? "muted" : "error"}>{status}</FileSheetStatusText> : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function RenderSettingsContent({
  enabled,
  scene,
  onEnabledChange,
  onStudioChange,
  onQualityChange,
  onSettingsValueChange,
  onReset,
  onCopyPayload,
  onApplyPayload
}) {
  const [activeLight, setActiveLight] = useState("directional");
  const payload = scene.render.payload;
  const settings = scene.render.settings;
  const effectiveStudioLabel = STUDIO_OPTIONS.find(({ value }) => value === scene.render.studio)?.label || "Light studio";
  const selectedLight = settings.lighting[activeLight] || { enabled: false, position: { x: 0, y: 0, z: 0 } };
  const setValue = (path, value) => onSettingsValueChange?.(path, value);

  return (
    <div className="py-2" data-cad-render-settings-section="true">
      <FileSheetSubsection
        title="Render"
        trailing={(
          <FileSheetToggleRow
            label="Enabled"
            checked={enabled}
            onCheckedChange={onEnabledChange}
            className="min-h-0 px-0"
          />
        )}
      >
        {enabled ? (
          <>
            <FileSheetSelectRow
              stacked
              label="Studio"
              value={payload.studio || ""}
              onValueChange={onStudioChange}
              options={STUDIO_OPTIONS}
              triggerContent={<span className="truncate">{effectiveStudioLabel}</span>}
            />
            <FileSheetSelectRow
              label="Quality"
              value={payload.quality}
              onValueChange={onQualityChange}
              options={SCENE_QUALITY_PRESETS.map((preset) => ({ value: preset.id, label: preset.label }))}
            />
          </>
        ) : null}
        <DebugSettings payload={payload} onCopyPayload={onCopyPayload} onApplyPayload={onApplyPayload} />
        <FileSheetButtonRow columns={1}>
          <Button type="button" variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={onReset}>
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Reset
          </Button>
        </FileSheetButtonRow>
      </FileSheetSubsection>

      {enabled ? (
        <>
          <FileSheetSubsection title="Output">
            <RenderSlider label="Exposure" value={settings.lighting.toneMappingExposure} min={0.05} max={6} onChange={(value) => setValue(["lighting", "toneMappingExposure"], value)} />
          </FileSheetSubsection>

          <FileSheetSubsection title="Material">
            <RenderSlider label="Roughness" value={settings.materials.roughness} min={0} max={1} onChange={(value) => setValue(["materials", "roughness"], value)} />
            <RenderSlider label="Metalness" value={settings.materials.metalness} min={0} max={1} onChange={(value) => setValue(["materials", "metalness"], value)} />
            <RenderSlider label="Clearcoat" value={settings.materials.clearcoat} min={0} max={1} onChange={(value) => setValue(["materials", "clearcoat"], value)} />
            <RenderSlider label="Reflections" value={settings.materials.envMapIntensity} min={0} max={4} onChange={(value) => setValue(["materials", "envMapIntensity"], value)} />
          </FileSheetSubsection>

          <FileSheetSubsection title="Color grading">
            <RenderSlider label="Saturation" value={settings.materials.saturation} min={0} max={2.5} onChange={(value) => setValue(["materials", "saturation"], value)} />
            <RenderSlider label="Contrast" value={settings.materials.contrast} min={0} max={2.5} onChange={(value) => setValue(["materials", "contrast"], value)} />
            <RenderSlider label="Brightness" value={settings.materials.brightness} min={0} max={2} onChange={(value) => setValue(["materials", "brightness"], value)} />
          </FileSheetSubsection>

          <FileSheetSubsection title="Backdrop">
            <FileSheetSelectRow label="Type" value={settings.background.type} onValueChange={(value) => setValue(["background", "type"], value)} options={BACKGROUND_OPTIONS} />
            {settings.background.type === "solid" ? <FileSheetColorRow label="Color" value={settings.background.solidColor} onChange={(value) => setValue(["background", "solidColor"], value)} /> : null}
            {settings.background.type === "linear" ? (
              <>
                <FileSheetColorRow label="Start color" value={settings.background.linearStart} onChange={(value) => setValue(["background", "linearStart"], value)} />
                <FileSheetColorRow label="End color" value={settings.background.linearEnd} onChange={(value) => setValue(["background", "linearEnd"], value)} />
                <RenderSlider label="Angle" value={settings.background.linearAngle} min={-360} max={360} step={1} digits={0} unit="°" onChange={(value) => setValue(["background", "linearAngle"], value)} />
              </>
            ) : null}
            {settings.background.type === "radial" ? (
              <>
                <FileSheetColorRow label="Inner color" value={settings.background.radialInner} onChange={(value) => setValue(["background", "radialInner"], value)} />
                <FileSheetColorRow label="Outer color" value={settings.background.radialOuter} onChange={(value) => setValue(["background", "radialOuter"], value)} />
              </>
            ) : null}
          </FileSheetSubsection>

          <FileSheetSubsection
            title="Floor"
            trailing={<FileSheetToggleRow label="Floor" checked={settings.floor.enabled} onCheckedChange={(value) => setValue(["floor", "enabled"], value)} className="min-h-0 px-0" />}
          >
            {settings.floor.enabled ? (
              <>
                <FileSheetToggleRow label="Follow model" checked={settings.floor.followModel !== false} onCheckedChange={(value) => setValue(["floor", "followModel"], value)} />
                <FileSheetColorRow label="Color" value={settings.floor.color} onChange={(value) => setValue(["floor", "color"], value)} />
                <RenderSlider label="Roughness" value={settings.floor.roughness} min={0} max={1} onChange={(value) => setValue(["floor", "roughness"], value)} />
                <RenderSlider label="Reflectivity" value={settings.floor.reflectivity} min={0} max={1} onChange={(value) => setValue(["floor", "reflectivity"], value)} />
                <RenderSlider label="Shadow" value={settings.floor.shadowOpacity} min={0} max={1} onChange={(value) => setValue(["floor", "shadowOpacity"], value)} />
                <RenderSlider label="Backdrop blend" value={settings.floor.horizonBlend} min={0} max={1} onChange={(value) => setValue(["floor", "horizonBlend"], value)} />
              </>
            ) : null}
          </FileSheetSubsection>

          <FileSheetSubsection
            title="Environment"
            trailing={<FileSheetToggleRow label="Environment" checked={settings.environment.enabled} onCheckedChange={(value) => setValue(["environment", "enabled"], value)} className="min-h-0 px-0" />}
          >
            {settings.environment.enabled ? (
              <>
                <FileSheetSelectRow label="Map" value={settings.environment.presetId} onValueChange={(value) => setValue(["environment", "presetId"], value)} options={ENVIRONMENT_PRESETS.map((preset) => ({ value: preset.id, label: preset.label }))} />
                <RenderSlider label="Intensity" value={settings.environment.intensity} min={0} max={4} onChange={(value) => setValue(["environment", "intensity"], value)} />
                <RenderSlider label="Rotation" value={(settings.environment.rotationY * 180) / Math.PI} min={-180} max={180} step={1} digits={0} unit="°" onChange={(value) => setValue(["environment", "rotationY"], (value * Math.PI) / 180)} />
                <FileSheetToggleRow label="Use as backdrop" checked={settings.environment.useAsBackground} onCheckedChange={(value) => setValue(["environment", "useAsBackground"], value)} />
              </>
            ) : null}
          </FileSheetSubsection>

          <FileSheetSubsection
            title="Lights"
            trailing={<FileSheetToggleRow label="Light" checked={selectedLight.enabled} onCheckedChange={(value) => setValue(["lighting", activeLight, "enabled"], value)} className="min-h-0 px-0" />}
          >
            <FileSheetSelectRow label="Light" value={activeLight} onValueChange={setActiveLight} options={LIGHT_OPTIONS} />
            {selectedLight.enabled ? (
              <>
                <FileSheetColorRow label="Color" value={selectedLight.color} onChange={(value) => setValue(["lighting", activeLight, "color"], value)} />
                <RenderSlider label="Intensity" value={selectedLight.intensity} min={0} max={20} onChange={(value) => setValue(["lighting", activeLight, "intensity"], value)} />
                {activeLight === "spot" ? <RenderSlider label="Angle" value={(selectedLight.angle * 180) / Math.PI} min={1} max={90} step={1} digits={0} unit="°" onChange={(value) => setValue(["lighting", activeLight, "angle"], (value * Math.PI) / 180)} /> : null}
                {activeLight === "spot" || activeLight === "point" ? <RenderSlider label="Distance" value={selectedLight.distance} min={0} max={5000} step={1} digits={0} onChange={(value) => setValue(["lighting", activeLight, "distance"], value)} /> : null}
                <PositionFields value={selectedLight.position} onChange={(axis, value) => setValue(["lighting", activeLight, "position", axis], value)} />
              </>
            ) : null}
          </FileSheetSubsection>

          <FileSheetSubsection
            title="Ambient"
            trailing={<FileSheetToggleRow label="Ambient" checked={settings.lighting.ambient.enabled} onCheckedChange={(value) => setValue(["lighting", "ambient", "enabled"], value)} className="min-h-0 px-0" />}
          >
            {settings.lighting.ambient.enabled ? (
              <>
                <FileSheetColorRow label="Color" value={settings.lighting.ambient.color} onChange={(value) => setValue(["lighting", "ambient", "color"], value)} />
                <RenderSlider label="Intensity" value={settings.lighting.ambient.intensity} min={0} max={20} onChange={(value) => setValue(["lighting", "ambient", "intensity"], value)} />
              </>
            ) : null}
          </FileSheetSubsection>

          <FileSheetSubsection
            title="Hemisphere"
            trailing={<FileSheetToggleRow label="Hemisphere" checked={settings.lighting.hemisphere.enabled} onCheckedChange={(value) => setValue(["lighting", "hemisphere", "enabled"], value)} className="min-h-0 px-0" />}
          >
            {settings.lighting.hemisphere.enabled ? (
              <>
                <FileSheetColorRow label="Sky color" value={settings.lighting.hemisphere.skyColor} onChange={(value) => setValue(["lighting", "hemisphere", "skyColor"], value)} />
                <FileSheetColorRow label="Ground color" value={settings.lighting.hemisphere.groundColor} onChange={(value) => setValue(["lighting", "hemisphere", "groundColor"], value)} />
                <RenderSlider label="Intensity" value={settings.lighting.hemisphere.intensity} min={0} max={20} onChange={(value) => setValue(["lighting", "hemisphere", "intensity"], value)} />
              </>
            ) : null}
          </FileSheetSubsection>

        </>
      ) : null}
    </div>
  );
}

export function buildRenderSettingsTab(props) {
  return {
    id: FILE_SHEET_SECTION_IDS.THEME_RENDER,
    title: "Render",
    content: <RenderSettingsContent {...props} />
  };
}
