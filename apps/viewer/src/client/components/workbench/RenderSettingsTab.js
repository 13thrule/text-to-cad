import { useState } from "react";
import { ClipboardPaste, Copy, RotateCcw } from "lucide-react";
import { RENDER_QUALITY_PRESETS, RENDER_STUDIO_PRESETS } from "cadgen-js/common/sceneSettings.js";
import { copyTextToClipboard } from "@/ui/clipboard";
import { cn } from "@/ui/utils";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import { Button } from "../ui/button";
import { Slider } from "../ui/slider";
import { Textarea } from "../ui/textarea";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorRow,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet";

const STUDIO_OPTIONS = Object.freeze(RENDER_STUDIO_PRESETS.map((preset) => ({
  value: preset.id,
  label: preset.label
})));

const QUALITY_OPTIONS = Object.freeze(RENDER_QUALITY_PRESETS.map((preset) => ({
  value: preset.id,
  label: preset.label
})));

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

function RenderSlider({ label, value, min, max, step = 0.01, unit = "", digits = 2, onChange }) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
  return (
    <FileSheetSliderField
      label={label}
      value={`${formatNumber(numericValue, digits)}${unit}`}
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

function RenderSettingsClipboard({ payload, onCopyPayload, onApplyPayload }) {
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
    <div className="space-y-3">
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
      {status ? (
        <FileSheetStatusText tone={status.includes("applied") || status.includes("copied") ? "muted" : "error"}>
          {status}
        </FileSheetStatusText>
      ) : null}
    </div>
  );
}

function RenderSettingsContent({
  enabled,
  scene,
  onEnabledChange,
  onStudioChange,
  onQualityChange,
  onPayloadValueChange,
  onReset,
  onCopyPayload,
  onApplyPayload
}) {
  const payload = scene.render.payload || {};
  const configuration = scene.render.configuration;
  const effectiveStudioLabel = STUDIO_OPTIONS.find(({ value }) => value === configuration.studio)?.label || "Light studio";
  const effectiveQualityLabel = QUALITY_OPTIONS.find(({ value }) => value === configuration.quality)?.label || "Final";
  const setValue = (path, value) => onPayloadValueChange?.(path, value);

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
          value={payload.quality || ""}
          onValueChange={onQualityChange}
          options={QUALITY_OPTIONS}
          triggerContent={<span className="truncate">{effectiveQualityLabel}</span>}
        />
        <RenderSettingsClipboard payload={payload} onCopyPayload={onCopyPayload} onApplyPayload={onApplyPayload} />
        <FileSheetButtonRow columns={1}>
          <Button type="button" variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={onReset}>
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Reset
          </Button>
        </FileSheetButtonRow>
      </FileSheetSubsection>

      {enabled ? (
        <>
          <FileSheetSubsection title="Camera">
            <RenderSlider label="Lens" value={scene.camera.focalLength} min={20} max={200} step={1} unit=" mm" digits={0} onChange={(value) => setValue(["camera", "focalLength"], value)} />
            <RenderSlider label="Exposure" value={configuration.exposure} min={-5} max={5} step={0.1} unit=" EV" digits={1} onChange={(value) => setValue(["exposure"], value)} />
          </FileSheetSubsection>

          <FileSheetSubsection title="Lighting">
            <RenderSlider label="Rotation" value={configuration.lighting.rotation} min={-180} max={180} step={1} unit="°" digits={0} onChange={(value) => setValue(["lighting", "rotation"], value)} />
            <RenderSlider label="Softbox size" value={configuration.lighting.size} min={0.25} max={3} step={0.05} digits={2} onChange={(value) => setValue(["lighting", "size"], value)} />
            <RenderSlider label="Fill ratio" value={configuration.lighting.fill} min={0} max={1} step={0.01} digits={2} onChange={(value) => setValue(["lighting", "fill"], value)} />
          </FileSheetSubsection>

          <FileSheetSubsection title="Backdrop">
            <FileSheetToggleRow label="Transparent" checked={configuration.backdrop.transparent} onCheckedChange={(value) => setValue(["backdrop", "transparent"], value)} />
            <FileSheetColorRow label="Color" value={configuration.backdrop.color} disabled={configuration.backdrop.transparent} onChange={(value) => setValue(["backdrop", "color"], value)} />
            <FileSheetToggleRow label="Ground" checked={configuration.backdrop.ground} onCheckedChange={(value) => setValue(["backdrop", "ground"], value)} />
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
