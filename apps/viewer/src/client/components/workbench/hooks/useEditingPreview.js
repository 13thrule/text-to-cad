import { useEffect, useMemo, useState } from "react";
import {
  editingPreviewEntry, editingPreviewLabel, initialEditingPreview, reduceEditingPreview,
} from "../../../workbench/editingPreview.js";

export function useEditingPreview(file, { enabled, catalogEntry } = {}) {
  const [snapshot, setSnapshot] = useState(() => ({ file: "", state: initialEditingPreview() }));
  useEffect(() => {
    if (!enabled || !file) return undefined;
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      let delay = 500;
      try {
        const response = await fetch(`/__cad/preview?file=${encodeURIComponent(file)}`, {
          signal: controller.signal, cache: "no-store",
        });
        if (!response.ok) throw new Error("Editing preview is unavailable");
        const next = await response.json();
        if (controller.signal.aborted) return;
        delay = ["submitted", "queued", "building"].includes(next.state) ? 100 : 500;
        setSnapshot(previous => {
          const before = previous.file === file ? previous.state : initialEditingPreview();
          const state = reduceEditingPreview(before, next);
          return previous.file === file && JSON.stringify(before) === JSON.stringify(state)
            ? previous : { file, state };
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setSnapshot(previous => ({ file, state: reduceEditingPreview(
          previous.file === file ? previous.state : initialEditingPreview(), { error: error.message },
        ) }));
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, delay);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [file, enabled]);
  const state = useMemo(() => enabled && snapshot.file === file
    ? snapshot.state : initialEditingPreview(), [enabled, file, snapshot]);
  const entry = useMemo(() => editingPreviewEntry(state, catalogEntry), [
    state.preview, state.revision, state.output, state.file,
    state.previewUnavailable,
    state.saved?.tree, state.saved?.documentHash,
    state.retainedSaved?.tree, state.retainedSaved?.documentHash, catalogEntry,
  ]);
  return { entry, state, label: editingPreviewLabel(state, Boolean(entry)) };
}
