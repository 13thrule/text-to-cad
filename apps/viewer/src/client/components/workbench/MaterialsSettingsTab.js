import { useEffect, useMemo, useState } from "react";
import { Check, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import {
  applyMaterialChoice,
  materialForSelection,
  sourceMaterialOverlayIsEmpty,
  MATERIAL_FINISH_PRESETS,
  duplicateSourceMaterialOverlay,
  effectiveSourceAppearance,
  patchSourceMaterialOverlay,
  sourceAppearanceHasMaterials,
  sourceMaterialFallbackColor,
  sourceMaterialEditorValue
} from "@/workbench/sourceMaterialSession";
import { Button } from "../ui/button";
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

function MaterialsSettingsContent({ appearance, overlay, targets = [], selectedPartIds = [], onSelectParts, onOverlayChange, scope = "" }) {
  const effective = useMemo(() => effectiveSourceAppearance(appearance, overlay), [appearance, overlay]);
  const parts = targets.filter(target => !target.group).map((part, index, all) => ({ ...part,
    label: /^=>\[/.test(part.label) ? all.length === 1 ? scope.split("/").pop().replace(/\.step$/i, "") : `Part ${index + 1}` : part.label
  }));
  const selected = parts.filter(part => selectedPartIds.includes(part.occurrenceIds[0]));
  const ids = selected.map(part => part.occurrenceIds[0]);
  const current = materialForSelection(effective, ids);
  const material = effective?.materials?.[current.materialId];
  const usage = Object.values(effective?.assignments || {}).filter(id => id === current.materialId).length;
  const selectionKey = JSON.stringify([scope, ids, current.materialId]);
  const [choice, setChoice] = useState("");
  const [editingShared, setEditingShared] = useState(false);
  useEffect(() => { setChoice(""); setEditingShared(false); }, [selectionKey]);
  const title = selected.length === 1 ? selected[0].label : `${selected.length} parts`;
  const fallbackColor = sourceMaterialFallbackColor(effective, current.materialId, parts.map(part => ({ id: part.occurrenceIds[0], color: part.color })));
  const sharedOutsideSelection = material && usage > ids.length;
  const editable = material && (!sharedOutsideSelection || editingShared);
  const change = (key, value) => onOverlayChange?.(patchSourceMaterialOverlay(overlay, current.materialId, { [key]: value }));
  const chosenName = choice.startsWith("material:") ? effective?.materials?.[choice.slice(9)]?.name
    : MATERIAL_FINISH_PRESETS.find(preset => `preset:${preset.id}` === choice)?.name;
  const swatch = (materialId, partColor) => <span aria-hidden="true" className="size-4 shrink-0 rounded-full border border-border"
    style={{ backgroundColor: sourceMaterialEditorValue(effective?.materials?.[materialId], "baseColor",
      partColor || sourceMaterialFallbackColor(effective, materialId, parts.map(part => ({ id: part.occurrenceIds[0], color: part.color })))) }} />;
  const partList = (list) => <div className="max-h-40 overflow-y-auto px-2 pb-1">
    {list.map(part => {
      const id = part.occurrenceIds[0];
      const assignedId = effective?.assignments?.[id];
      return <button key={id} type="button" aria-pressed={ids.includes(id)}
        onClick={event => onSelectParts?.(event.shiftKey ? ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id] : [id])}
        className={cn("flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11px] hover:bg-accent/60", ids.includes(id) && "bg-accent")}>
        {swatch(assignedId, part.color)}<span className="min-w-0 flex-1 break-words">{part.label}</span>
        <span className="text-muted-foreground">{effective?.materials?.[assignedId]?.name || "Unassigned"}</span>
        {ids.includes(id) ? <Check aria-hidden="true" className="size-3 shrink-0" /> : null}
      </button>;
    })}
  </div>;
  const optionList = (label, options) => <FileSheetSubsection title={label}>
    <div className="grid grid-cols-2 gap-1 px-2" role="radiogroup" aria-label={label}>
      {options.map(option => <button key={option.value} type="button" role="radio" aria-checked={choice === option.value}
        onClick={() => setChoice(option.value)}
        className={cn("flex min-h-8 w-full items-center justify-between rounded border px-2 text-left text-[11px]",
          choice === option.value ? "border-primary bg-accent text-accent-foreground" : "border-border/60 text-muted-foreground hover:bg-accent/60")}>
        <span>{option.label}</span>{choice === option.value ? <Check className="size-3.5" /> : null}
      </button>)}
    </div>
  </FileSheetSubsection>;
  return <div className="py-2" data-cad-materials-settings-section="true">
    <FileSheetSubsection title={ids.length ? `${title} selected` : "Selected parts"}>
      <FileSheetStatusText>{ids.length ? `Current material: ${current.label}` : "Click a part to assign a material. Shift-click to select multiple, or select parts from the lists below."}</FileSheetStatusText>
      {ids.length ? partList(selected) : null}
      <FileSheetButtonRow columns={ids.length ? 2 : 1}>
        <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} disabled={!parts.length}
          onClick={() => onSelectParts?.(parts.map(part => part.occurrenceIds[0]))}>Select all parts</Button>
        {ids.length ? <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={() => onSelectParts?.([])}>Clear selection</Button> : null}
      </FileSheetButtonRow>
    </FileSheetSubsection>
    <FileSheetSubsection title="In this model">
      <div className="space-y-1 px-2" role="radiogroup" aria-label="In this model">
        {Object.entries(effective?.materials || {}).map(([id, entry]) => {
          const assigned = parts.filter(part => effective?.assignments?.[part.occurrenceIds[0]] === id);
          return <div key={id} className="rounded border border-border/60">
            <button type="button" role="radio" aria-checked={choice === `material:${id}`}
              onClick={() => setChoice(`material:${id}`)}
              className={cn("flex w-full items-center gap-2 rounded px-2 py-2 text-left text-[11px] hover:bg-accent/60", choice === `material:${id}` && "bg-accent ring-1 ring-primary")}>
              {swatch(id)}<span className="flex-1 break-words">{entry.name}</span>
              {ids.length > 0 && current.materialId === id ? <span className="text-muted-foreground">Assigned</span> : null}
              {choice === `material:${id}` ? <Check aria-hidden="true" className="size-3.5" /> : null}
            </button>
            {assigned.length ? <details>
              <summary className="cursor-pointer px-2 pb-2 text-[11px] text-muted-foreground">{assigned.length} {assigned.length === 1 ? "part" : "parts"}</summary>
              <div className="px-2 pb-1"><Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
                onClick={() => onSelectParts?.(assigned.map(part => part.occurrenceIds[0]))}>Select parts using {entry.name}</Button></div>
              {partList(assigned)}
            </details> : <p className="px-2 pb-2 text-[11px] text-muted-foreground">Not assigned</p>}
          </div>;
        })}
      </div>
      {!Object.keys(effective?.materials || {}).length ? <FileSheetStatusText>No materials yet. Choose a preset to get started.</FileSheetStatusText> : null}
      {parts.some(part => !effective?.materials?.[effective?.assignments?.[part.occurrenceIds[0]]]) ? <details className="mx-2 mt-2 rounded border border-border/60">
        <summary className="cursor-pointer px-2 py-2 text-[11px]">Unassigned · {parts.filter(part => !effective?.materials?.[effective?.assignments?.[part.occurrenceIds[0]]]).length} parts</summary>
        {partList(parts.filter(part => !effective?.materials?.[effective?.assignments?.[part.occurrenceIds[0]]]))}
      </details> : null}
    </FileSheetSubsection>
      {optionList("Presets", MATERIAL_FINISH_PRESETS.map(preset => ({value: `preset:${preset.id}`, label: preset.name})))}
      <FileSheetButtonRow columns={1}>
        <Button size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} disabled={!choice || !ids.length}
          onClick={() => { const result = applyMaterialChoice(appearance, overlay, ids, choice); if (result) { onOverlayChange?.(result.overlay); setChoice(""); } }}>
          {ids.length ? `Apply${chosenName ? ` ${chosenName}` : " material"} to ${title}` : "Select parts to apply"}
        </Button>
      </FileSheetButtonRow>
      {ids.length && material ? <FileSheetSubsection title={`Edit ${material.name}`}>
        {sharedOutsideSelection ? <>
          <FileSheetStatusText>Shared by {usage} parts. Editing this material changes all of them.</FileSheetStatusText>
          <FileSheetButtonRow columns={1}>
            <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={() => setEditingShared(value => !value)}>{editingShared ? "Stop editing shared material" : "Edit shared material"}</Button>
            <Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={() => {
              const result = duplicateSourceMaterialOverlay(appearance, overlay, current.materialId, ids);
              if (result?.overlay) onOverlayChange?.(result.overlay);
            }}>Make unique for selection</Button>
          </FileSheetButtonRow>
        </> : null}
        {editable ? <>
          <FileSheetColorRow label="Base color" value={sourceMaterialEditorValue(material, "baseColor", fallbackColor)} onChange={value => change("baseColor", value)} />
          {[ ["Roughness", "roughness"], ["Metalness", "metalness"], ["Clearcoat", "clearcoat"], ["Coat roughness", "clearcoatRoughness"], ["Opacity", "opacity"] ].map(([label, key]) =>
            <MaterialSlider key={key} label={label} value={sourceMaterialEditorValue(material, key)} onChange={value => change(key, value)} />)}
        </> : null}
      </FileSheetSubsection> : null}
    <FileSheetStatusText>Edits are remembered in this browser tab. Source files are unchanged.</FileSheetStatusText>
    <FileSheetButtonRow columns={1}><Button variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
      disabled={sourceMaterialOverlayIsEmpty(overlay)} onClick={() => onOverlayChange?.(null)}><RotateCcw className="size-3.5" />Reset authored</Button></FileSheetButtonRow>
  </div>;
}

export function buildMaterialsSettingsTab(props = {}) {
  if (!props.enabled && !sourceAppearanceHasMaterials(props.appearance)) return null;
  return { id: FILE_SHEET_SECTION_IDS.THEME_MATERIALS, title: "Materials", content: <MaterialsSettingsContent {...props} /> };
}
