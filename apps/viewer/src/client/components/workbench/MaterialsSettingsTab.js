import { useEffect, useMemo, useState } from "react";
import { Check, CopyPlus, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import {
  assignSourceMaterialOverlay,
  duplicateSourceMaterialOverlay,
  effectiveSourceAppearance,
  patchSourceMaterialOverlay,
  sourceAppearanceHasMaterials,
  sourceMaterialFallbackColor,
  sourceMaterialEditorValue,
  sourceMaterialUsage
} from "@/workbench/sourceMaterialSession";
import { Button } from "../ui/button";
import { ScrollArea } from "../ui/scroll-area";
import { Slider } from "../ui/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  parseFileSheetNumberInput
} from "./FileSheet";

function clampUnit(value) {
  return Math.min(Math.max(Number(value) || 0, 0), 1);
}

function MaterialSlider({ label, value, onChange }) {
  const numericValue = clampUnit(value);
  return (
    <FileSheetSliderField
      label={label}
      value={numericValue.toFixed(2)}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, {
        fallback: numericValue,
        min: 0,
        max: 1
      }))}
      valueInputProps={{ ariaLabel: `${label} value` }}
    >
      <Slider
        value={[numericValue]}
        min={0}
        max={1}
        step={0.01}
        onValueChange={(next) => onChange(clampUnit(next[0]))}
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        aria-label={label}
      />
    </FileSheetSliderField>
  );
}

function selectedOccurrenceIds(targets, selectedTargetIds) {
  const selected = new Set(selectedTargetIds);
  return [...new Set(targets
    .filter((target) => selected.has(target.id))
    .flatMap((target) => target.occurrenceIds || []))];
}

function MaterialsSettingsContent({ appearance, overlay, targets = [], onOverlayChange, scope = "" }) {
  const effective = useMemo(() => effectiveSourceAppearance(appearance, overlay), [appearance, overlay]);
  const materials = effective?.materials || {};
  const materialIds = Object.keys(materials);
  const [selectedMaterialId, setSelectedMaterialId] = useState(materialIds[0] || "");
  const [selectedTargetIds, setSelectedTargetIds] = useState([]);

  useEffect(() => {
    setSelectedMaterialId((current) => materials[current] ? current : materialIds[0] || "");
    setSelectedTargetIds([]);
  }, [scope]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!materials[selectedMaterialId]) setSelectedMaterialId(materialIds[0] || "");
  }, [materialIds.join("|"), materials, selectedMaterialId]); // eslint-disable-line react-hooks/exhaustive-deps

  const usage = useMemo(
    () => sourceMaterialUsage(appearance, overlay, targets.flatMap((target) => (
      target.group ? [] : [{ id: target.occurrenceIds?.[0] }]
    ))),
    [appearance, overlay, targets]
  );
  const materialParts = useMemo(() => targets.filter((target) => !target.group).map((target) => ({
    id: target.occurrenceIds?.[0],
    color: target.color
  })), [targets]);
  const fallbackColors = useMemo(() => Object.fromEntries(materialIds.map((materialId) => [
    materialId,
    sourceMaterialFallbackColor(effective, materialId, materialParts)
  ])), [effective, materialIds.join("|"), materialParts]); // eslint-disable-line react-hooks/exhaustive-deps
  const material = materials[selectedMaterialId] || null;
  const occurrenceIds = selectedOccurrenceIds(targets, selectedTargetIds);
  const fallbackColor = fallbackColors[selectedMaterialId] || "#b8b8b8";
  const changeChannel = (key, value) => {
    onOverlayChange?.(patchSourceMaterialOverlay(overlay, selectedMaterialId, { [key]: value }));
  };
  const toggleTarget = (targetId) => {
    setSelectedTargetIds((current) => current.includes(targetId)
      ? current.filter((id) => id !== targetId)
      : [...current, targetId]);
  };
  const duplicateForSelection = () => {
    const result = duplicateSourceMaterialOverlay(appearance, overlay, selectedMaterialId, occurrenceIds);
    if (!result?.overlay) return;
    onOverlayChange?.(result.overlay);
    setSelectedMaterialId(result.materialId);
  };

  return (
    <div className="py-2" data-cad-materials-settings-section="true">
      <FileSheetSubsection title="Materials">
        <div className="space-y-1 px-2" role="listbox" aria-label="Materials">
          {materialIds.map((materialId) => {
            const entry = materials[materialId];
            const selected = materialId === selectedMaterialId;
            return (
              <button
                key={materialId}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn(
                  "flex h-8 w-full items-center gap-2 rounded px-2 text-left text-[11px] transition-colors",
                  selected ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                )}
                onClick={() => setSelectedMaterialId(materialId)}
              >
                <span
                  className="size-4 shrink-0 rounded-sm border border-border shadow-inner"
                  style={{ backgroundColor: sourceMaterialEditorValue(entry, "baseColor", fallbackColors[materialId]) }}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate font-medium">{entry.name}</span>
                <span className="shrink-0 tabular-nums opacity-70">{usage[materialId] || 0}</span>
              </button>
            );
          })}
        </div>
      </FileSheetSubsection>

      {material ? (
        <FileSheetSubsection title={material.name}>
          <FileSheetColorRow
            label="Base color"
            value={sourceMaterialEditorValue(material, "baseColor", fallbackColor)}
            onChange={(value) => changeChannel("baseColor", value)}
          />
          <MaterialSlider label="Roughness" value={sourceMaterialEditorValue(material, "roughness")} onChange={(value) => changeChannel("roughness", value)} />
          <MaterialSlider label="Metalness" value={sourceMaterialEditorValue(material, "metalness")} onChange={(value) => changeChannel("metalness", value)} />
          <MaterialSlider label="Clearcoat" value={sourceMaterialEditorValue(material, "clearcoat")} onChange={(value) => changeChannel("clearcoat", value)} />
          <MaterialSlider label="Coat roughness" value={sourceMaterialEditorValue(material, "clearcoatRoughness")} onChange={(value) => changeChannel("clearcoatRoughness", value)} />
          <MaterialSlider label="Opacity" value={sourceMaterialEditorValue(material, "opacity")} onChange={(value) => changeChannel("opacity", value)} />
        </FileSheetSubsection>
      ) : null}

      {material && targets.length ? (
        <FileSheetSubsection title="Assign to components">
          <ScrollArea className="mx-2 h-48 overflow-hidden rounded border border-border/60">
            <div className="p-1">
              {targets.map((target) => {
                const selected = selectedTargetIds.includes(target.id);
                return (
                  <button
                    key={target.id}
                    type="button"
                    className={cn(
                      "flex min-h-7 w-full items-center gap-2 rounded px-2 text-left text-[11px] transition-colors",
                      selected ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                    )}
                    style={{ paddingLeft: `${8 + Math.min(Number(target.depth) || 0, 4) * 10}px` }}
                    onClick={() => toggleTarget(target.id)}
                    aria-pressed={selected}
                  >
                    <span className={cn(
                      "grid size-3.5 shrink-0 place-items-center rounded-sm border",
                      selected ? "border-primary bg-primary text-primary-foreground" : "border-border"
                    )}>
                      {selected ? <Check className="size-2.5" aria-hidden="true" /> : null}
                    </span>
                    <span className={cn("min-w-0 flex-1 truncate", target.group && "font-medium text-foreground")}>{target.label}</span>
                    {target.group ? <span className="shrink-0 text-[10px] opacity-60">group</span> : null}
                  </button>
                );
              })}
            </div>
          </ScrollArea>
          {!occurrenceIds.length ? (
            <FileSheetStatusText>Select one or more components or groups.</FileSheetStatusText>
          ) : null}
          <FileSheetButtonRow columns={2}>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
              disabled={!occurrenceIds.length}
              onClick={() => onOverlayChange?.(assignSourceMaterialOverlay(overlay, occurrenceIds, selectedMaterialId))}
            >
              <Check className="size-3.5" aria-hidden="true" />
              Assign
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
              disabled={!occurrenceIds.length}
              onClick={duplicateForSelection}
            >
              <CopyPlus className="size-3.5" aria-hidden="true" />
              Duplicate
            </Button>
          </FileSheetButtonRow>
        </FileSheetSubsection>
      ) : null}

      <FileSheetButtonRow columns={1}>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
          disabled={!Object.keys(overlay?.materials || {}).length && !Object.keys(overlay?.assignments || {}).length}
          onClick={() => onOverlayChange?.(null)}
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
          Reset authored
        </Button>
      </FileSheetButtonRow>
    </div>
  );
}

export function buildMaterialsSettingsTab(props = {}) {
  if (!sourceAppearanceHasMaterials(props.appearance)) return null;
  return {
    id: FILE_SHEET_SECTION_IDS.THEME_MATERIALS,
    title: "Materials",
    content: <MaterialsSettingsContent {...props} />
  };
}
