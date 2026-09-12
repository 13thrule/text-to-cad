import FileSheet from "./FileSheet";
import FileSheetTabbedSurface from "./FileSheetTabbedSurface";
import StepMeasurementsSection from "./StepMeasurementsSection";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections";

const EMPTY_MEASUREMENTS = [];

// For kind="mesh", the Measure tab. DXF reuses this sheet with extra
// settingsTabs and does not pass measurements.
export default function MeshFileSheet({
  open,
  kind = "mesh",
  title = "Mesh",
  isDesktop,
  width,
  selectedEntry = null,
  onOpenChange,
  onStartResize,
  viewerServerInfo = null,
  suppressDynamicMetadataStatus = false,
  renderMode = false,
  settingsTabs = [],
  openSectionIds = [],
  onOpenSectionIdsChange,
  measurements = EMPTY_MEASUREMENTS,
  activeMeasurementId = "",
  measureModeActive = false,
  onMeasurementActivate = null,
  onMeasurementDelete = null,
  onMeasurementsClear = null
}) {
  const measureTab = kind === "mesh"
    ? {
      id: FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS,
      title: "Measure",
      content: (
        <StepMeasurementsSection
          measurements={measurements}
          activeId={activeMeasurementId}
          measureModeActive={measureModeActive}
          onActivate={onMeasurementActivate}
          onDelete={onMeasurementDelete}
          onClear={onMeasurementsClear}
        />
      )
    }
    : null;
  const allSections = [
    ...(measureTab ? [measureTab] : []),
    ...settingsTabs
  ];
  const sections = renderMode
    ? allSections.filter((section) => section?.id === FILE_SHEET_SECTION_IDS.THEME_RENDER)
    : allSections;

  return (
    <FileSheet
      open={open}
      title={title}
      isDesktop={isDesktop}
      width={width}
      onOpenChange={onOpenChange}
      onStartResize={onStartResize}
      scrollBody={false}
    >
      <FileSheetTabbedSurface
        kind={kind}
        layoutMode={renderMode ? "render" : "cad"}
        layoutScope={selectedEntry?.rootRelativeFile || selectedEntry?.file || ""}
        sections={sections}
        openSectionIds={openSectionIds}
        onOpenSectionIdsChange={onOpenSectionIdsChange}
      />
    </FileSheet>
  );
}
