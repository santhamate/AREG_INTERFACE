/**
 * ScenarioGenerator Component
 *
 * Provides a complete UI for generating AREG800A OSI scenario files.
 * Features:
 * - Template selection (Range Sweep, Constant Object, Multi-Object, Azimuth Sweep)
 * - Parameter configuration for each template
 * - Real-time preview and validation
 * - File generation with local storage
 * - Integration with scenario player
 *
 * Single-page layout with expandable dropdown menus
 * Requires: osi3 Python package on backend (>=3.5.0)
 */

import { useEffect, useState } from "react";
import "./ScenarioGenerator.css";

type TemplateType = "range_sweep" | "constant_object" | "multi_object" | "azimuth_sweep" | "constant_echo_power";

interface ScenarioPreview {
  duration_s: number;
  message_count: number;
  object_count: number;
  min_range_m: number;
  max_range_m: number;
  min_azimuth_deg: number;
  max_azimuth_deg: number;
  min_velocity_mps: number;
  max_velocity_mps: number;
  min_rcs_dbsm: number;
  max_rcs_dbsm: number;
  estimated_file_size_bytes: number;
  warnings: string[];
}

interface GenerationResponse {
  ok: boolean;
  file_path: string | null;
  message_count: number;
  duration_s: number;
  preview: ScenarioPreview | null;
  rcs_table: { range_m: number; rcs_dbsm: number }[] | null;
  error: string | null;
}

interface GeneratorStatus {
  osi_available: boolean;
  osi_error: string | null;
  last_generated_file: string | null;
  last_preview: ScenarioPreview | null;
}

interface SessionState {
  connected: boolean;
}

interface UploadOsiResponse {
  ok: boolean;
  remote_path: string | null;
  error?: string | null;
}

interface DiscoverDeviceDirectoriesResponse {
  ok: boolean;
  directories: string[];
  error?: string;
}

interface MultiObject {
  name: string;
  enabled: boolean;
  start_range_m: number;
  stop_range_m: number;
  radial_velocity_mps: number;
  rcs_dbsm: number;
  azimuth_deg: number;
  elevation_deg: number;
}

const API_BASE = "http://127.0.0.1:8000/api";

export default function ScenarioGenerator() {
  const [generatorStatus, setGeneratorStatus] = useState<GeneratorStatus>({
    osi_available: false,
    osi_error: null,
    last_generated_file: null,
    last_preview: null,
  });

  const [selectedTemplate, setSelectedTemplate] = useState<TemplateType>("range_sweep");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationResult, setGenerationResult] = useState<GenerationResponse | null>(null);
  const [lastPreview, setLastPreview] = useState<ScenarioPreview | null>(null);
  const [autoUploadStatus, setAutoUploadStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [selectedUploadDirectory, setSelectedUploadDirectory] = useState<string | null>(null);

  const [rangeSweepParams, setRangeSweepParams] = useState({
    output_dir: "./scenarios",
    output_filename: "range_sweep",
    sensor_id: 1,
    update_interval_s: 0.1,
    start_range_m: 120,
    stop_range_m: 20,
    radial_velocity_mps: -10,
    rcs_dbsm: 10,
    azimuth_deg: 0,
    elevation_deg: 0,
    scenario_name: "range_sweep",
  });

  const [constantObjectParams, setConstantObjectParams] = useState({
    output_dir: "./scenarios",
    output_filename: "constant_object",
    sensor_id: 1,
    duration_s: 10,
    update_interval_s: 0.1,
    range_m: 100,
    radial_velocity_mps: 0,
    rcs_dbsm: 10,
    azimuth_deg: 0,
    elevation_deg: 0,
    scenario_name: "constant_object",
  });

  const [multiObjectParams, setMultiObjectParams] = useState({
    output_dir: "./scenarios",
    output_filename: "multi_object",
    sensor_id: 1,
    update_interval_s: 0.1,
    duration_s: 10,
    objects: [
      {
        name: "obj_1",
        enabled: true,
        start_range_m: 120,
        stop_range_m: 40,
        radial_velocity_mps: -8,
        rcs_dbsm: 10,
        azimuth_deg: 0,
        elevation_deg: 0,
      },
    ] as MultiObject[],
    scenario_name: "multi_object",
  });

  const [azimuthSweepParams, setAzimuthSweepParams] = useState({
    output_dir: "./scenarios",
    output_filename: "azimuth_sweep",
    sensor_id: 1,
    update_interval_s: 0.1,
    duration_s: 10,
    range_m: 100,
    start_azimuth_deg: -90,
    stop_azimuth_deg: 90,
    radial_velocity_mps: 0,
    rcs_dbsm: 10,
    elevation_deg: 0,
    scenario_name: "azimuth_sweep",
  });

  const [constEchoPowerParams, setConstEchoPowerParams] = useState({
    output_dir: "./scenarios",
    output_filename: "constant_echo_power",
    sensor_id: 1,
    update_interval_s: 0.1,
    start_range_m: 120,
    stop_range_m: 20,
    radial_velocity_mps: -10,
    ref_rcs_dbsm: 10,
    ref_range_m: 100,
    azimuth_deg: 0,
    elevation_deg: 0,
    rcs_min_dbsm: -30,
    rcs_max_dbsm: 60,
    scenario_name: "constant_echo_power",
  });

  // Fetch generator status on mount
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/generator/status`);
        if (res.ok) {
          const data = (await res.json()) as GeneratorStatus;
          setGeneratorStatus(data);
        }
      } catch (err) {
        console.error("Failed to fetch generator status:", err);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const generateScenario = async (endpoint: string, payload: object) => {
    setIsGenerating(true);
    setGenerationResult(null);
    setAutoUploadStatus(null);
    setSelectedUploadDirectory(null);

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        throw new Error(data.detail ?? "Scenario generation failed");
      }

      const data = (await response.json()) as GenerationResponse;
      setGenerationResult(data);
      if (data.preview) {
        setLastPreview(data.preview);
      }
      if (data.ok && data.file_path) {
        await autoUploadGeneratedScenario(data.file_path);
      }
    } catch (error) {
      setGenerationResult({
        ok: false,
        file_path: null,
        message_count: 0,
        duration_s: 0,
        preview: null,
        rcs_table: null,
        error: error instanceof Error ? error.message : "Unknown generation error",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const discoverPreferredUsbDirectory = async (): Promise<string | null> => {
    try {
      const res = await fetch(`${API_BASE}/device/files/discover`);
      if (!res.ok) return null;
      const data = (await res.json()) as DiscoverDeviceDirectoriesResponse;
      if (!data.ok || !Array.isArray(data.directories) || data.directories.length === 0) return null;
      const sorted = [...data.directories].sort((a, b) => {
        const al = a.toLowerCase();
        const bl = b.toLowerCase();
        const ar = al.includes("usb") ? 0 : (al.includes("sd") || al.includes("mmc") || al.includes("mass_storage") ? 1 : 2);
        const br = bl.includes("usb") ? 0 : (bl.includes("sd") || bl.includes("mmc") || bl.includes("mass_storage") ? 1 : 2);
        if (ar !== br) return ar - br;
        return al.localeCompare(bl);
      });
      return sorted[0] ?? null;
    } catch {
      return null;
    }
  };

  const autoUploadGeneratedScenario = async (localPath: string) => {
    try {
      const sessionRes = await fetch(`${API_BASE}/session`);
      if (!sessionRes.ok) return;
      const session = (await sessionRes.json()) as SessionState;
      if (!session.connected) return;

      const preferredDir = await discoverPreferredUsbDirectory();
      if (preferredDir) {
        setSelectedUploadDirectory(preferredDir);
      }
      const uploadPayload: { local_path: string; preferred_directory?: string } = { local_path: localPath };
      if (preferredDir) {
        uploadPayload.preferred_directory = preferredDir;
      }

      const uploadRes = await fetch(`${API_BASE}/device/files/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(uploadPayload),
      });
      const uploadData = (await uploadRes.json()) as UploadOsiResponse;

      if (uploadRes.ok && uploadData.ok) {
        setAutoUploadStatus({
          ok: true,
          text: `Uploaded to device: ${uploadData.remote_path ?? "(unknown path)"}`,
        });
      } else {
        setAutoUploadStatus({
          ok: false,
          text: uploadData.error ?? "Auto-upload to device failed",
        });
      }
    } catch {
      setAutoUploadStatus({ ok: false, text: "Auto-upload to device failed" });
    }
  };

  const onGenerateRangeSweep = async () => {
    await generateScenario("/generator/range-sweep", rangeSweepParams);
  };

  const onGenerateConstantObject = async () => {
    await generateScenario("/generator/constant-object", constantObjectParams);
  };

  const onGenerateMultiObject = async () => {
    await generateScenario("/generator/multi-object", multiObjectParams);
  };

  const onGenerateAzimuthSweep = async () => {
    await generateScenario("/generator/azimuth-sweep", azimuthSweepParams);
  };

  const onGenerateConstantEchoPower = async () => {
    await generateScenario("/generator/constant-echo-power", constEchoPowerParams);
  };

  const updateMultiObject = (index: number, updates: Partial<MultiObject>) => {
    setMultiObjectParams({
      ...multiObjectParams,
      objects: multiObjectParams.objects.map((obj, i) => (i === index ? { ...obj, ...updates } : obj)),
    });
  };

  const addMultiObject = () => {
    const nextIndex = multiObjectParams.objects.length + 1;
    setMultiObjectParams({
      ...multiObjectParams,
      objects: [
        ...multiObjectParams.objects,
        {
          name: `obj_${nextIndex}`,
          enabled: true,
          start_range_m: 100,
          stop_range_m: 60,
          radial_velocity_mps: -4,
          rcs_dbsm: 8,
          azimuth_deg: 10 * (nextIndex - 1),
          elevation_deg: 0,
        },
      ],
    });
  };

  const removeMultiObject = (index: number) => {
    setMultiObjectParams({
      ...multiObjectParams,
      objects: multiObjectParams.objects.filter((_, i) => i !== index),
    });
  };

  const onTemplateChange = (value: TemplateType) => {
    setSelectedTemplate(value);
    setGenerationResult(null);
  };

  const prettyTemplateName = (template: TemplateType) => {
    if (template === "range_sweep") return "Range Sweep";
    if (template === "constant_object") return "Constant Object";
    if (template === "multi_object") return "Multi-Object";
    if (template === "constant_echo_power") return "Constant Echo Power";
    return "Azimuth Sweep";
  };

  if (!generatorStatus.osi_available) {
    return (
      <div className="scenario-generator error-state">
        <div className="error-banner">
          <h2>❌ OSI3 Package Not Available</h2>
          <p>{generatorStatus.osi_error}</p>
          <div className="install-steps">
            <h3>To enable scenario generation:</h3>
            <ol>
              <li>Install the OSI3 Python package:</li>
              <code>pip install osi3</code>
              <li>Minimum version: 3.5.0</li>
              <li>Restart the application</li>
            </ol>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="scenario-generator">
      <div className="generator-header">
        <h1>Scenario Generator</h1>
        <p>Single-page workflow with dropdown sections for template, parameters, preview, and result.</p>
      </div>

      <div className="generator-single-page">
        <details className="sg-dropdown" open>
          <summary>Template</summary>
          <div className="sg-dropdown-content">
            <div className="param-group">
              <label>Template Type:</label>
              <select value={selectedTemplate} onChange={(e) => onTemplateChange(e.target.value as TemplateType)}>
                <option value="range_sweep">Range Sweep</option>
                <option value="constant_object">Constant Object</option>
                <option value="multi_object">Multi-Object</option>
                <option value="azimuth_sweep">Azimuth Sweep</option>
                <option value="constant_echo_power">Constant Echo Power (R⁴)</option>
              </select>
            </div>
            <p className="description">Selected: {prettyTemplateName(selectedTemplate)}</p>
          </div>
        </details>

        <details className="sg-dropdown" open>
          <summary>Parameters</summary>
          <div className="sg-dropdown-content template-params">
            {selectedTemplate === "range_sweep" && (
              <>
                <h3>Range Sweep Parameters</h3>
                <div className="param-grid">
                  <div className="param-group"><label>Sensor ID</label><input type="number" min="1" value={rangeSweepParams.sensor_id} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, sensor_id: parseInt(e.target.value, 10) || 1 })} /></div>
                  <div className="param-group"><label>Update Interval (s)</label><input type="number" min="0.01" step="0.01" value={rangeSweepParams.update_interval_s} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, update_interval_s: parseFloat(e.target.value) || 0.01 })} /></div>
                  <div className="param-group"><label>Start Range (m)</label><input type="number" min="0" step="1" value={rangeSweepParams.start_range_m} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, start_range_m: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Stop Range (m)</label><input type="number" min="0" step="1" value={rangeSweepParams.stop_range_m} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, stop_range_m: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Radial Velocity (m/s)</label><input type="number" step="0.1" value={rangeSweepParams.radial_velocity_mps} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, radial_velocity_mps: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>RCS (dBsm)</label><input type="number" step="1" value={rangeSweepParams.rcs_dbsm} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, rcs_dbsm: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Azimuth (deg)</label><input type="number" min="-180" max="360" step="1" value={rangeSweepParams.azimuth_deg} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, azimuth_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Elevation (deg)</label><input type="number" min="-90" max="90" step="1" value={rangeSweepParams.elevation_deg} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, elevation_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Output Directory</label><input type="text" value={rangeSweepParams.output_dir} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, output_dir: e.target.value })} /></div>
                  <div className="param-group"><label>Output Filename</label><input type="text" value={rangeSweepParams.output_filename} onChange={(e) => setRangeSweepParams({ ...rangeSweepParams, output_filename: e.target.value })} /></div>
                </div>
                <button className="btn-generate" onClick={onGenerateRangeSweep} disabled={isGenerating}>Generate Range Sweep</button>
              </>
            )}

            {selectedTemplate === "constant_object" && (
              <>
                <h3>Constant Object Parameters</h3>
                <div className="param-grid">
                  <div className="param-group"><label>Sensor ID</label><input type="number" min="1" value={constantObjectParams.sensor_id} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, sensor_id: parseInt(e.target.value, 10) || 1 })} /></div>
                  <div className="param-group"><label>Duration (s)</label><input type="number" min="0.1" step="0.1" value={constantObjectParams.duration_s} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, duration_s: parseFloat(e.target.value) || 0.1 })} /></div>
                  <div className="param-group"><label>Update Interval (s)</label><input type="number" min="0.01" step="0.01" value={constantObjectParams.update_interval_s} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, update_interval_s: parseFloat(e.target.value) || 0.01 })} /></div>
                  <div className="param-group"><label>Range (m)</label><input type="number" min="0" step="1" value={constantObjectParams.range_m} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, range_m: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Radial Velocity (m/s)</label><input type="number" step="0.1" value={constantObjectParams.radial_velocity_mps} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, radial_velocity_mps: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>RCS (dBsm)</label><input type="number" step="1" value={constantObjectParams.rcs_dbsm} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, rcs_dbsm: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Azimuth (deg)</label><input type="number" min="-180" max="360" step="1" value={constantObjectParams.azimuth_deg} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, azimuth_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Elevation (deg)</label><input type="number" min="-90" max="90" step="1" value={constantObjectParams.elevation_deg} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, elevation_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Output Directory</label><input type="text" value={constantObjectParams.output_dir} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, output_dir: e.target.value })} /></div>
                  <div className="param-group"><label>Output Filename</label><input type="text" value={constantObjectParams.output_filename} onChange={(e) => setConstantObjectParams({ ...constantObjectParams, output_filename: e.target.value })} /></div>
                </div>
                <button className="btn-generate" onClick={onGenerateConstantObject} disabled={isGenerating}>Generate Constant Object</button>
              </>
            )}

            {selectedTemplate === "multi_object" && (
              <>
                <h3>Multi-Object Parameters</h3>
                <div className="param-grid">
                  <div className="param-group"><label>Sensor ID</label><input type="number" min="1" value={multiObjectParams.sensor_id} onChange={(e) => setMultiObjectParams({ ...multiObjectParams, sensor_id: parseInt(e.target.value, 10) || 1 })} /></div>
                  <div className="param-group"><label>Duration (s)</label><input type="number" min="0.1" step="0.1" value={multiObjectParams.duration_s} onChange={(e) => setMultiObjectParams({ ...multiObjectParams, duration_s: parseFloat(e.target.value) || 0.1 })} /></div>
                  <div className="param-group"><label>Update Interval (s)</label><input type="number" min="0.01" step="0.01" value={multiObjectParams.update_interval_s} onChange={(e) => setMultiObjectParams({ ...multiObjectParams, update_interval_s: parseFloat(e.target.value) || 0.01 })} /></div>
                  <div className="param-group"><label>Output Directory</label><input type="text" value={multiObjectParams.output_dir} onChange={(e) => setMultiObjectParams({ ...multiObjectParams, output_dir: e.target.value })} /></div>
                  <div className="param-group"><label>Output Filename</label><input type="text" value={multiObjectParams.output_filename} onChange={(e) => setMultiObjectParams({ ...multiObjectParams, output_filename: e.target.value })} /></div>
                </div>

                <div className="inline-actions">
                  <button type="button" className="btn-generate" onClick={addMultiObject}>Add Object</button>
                </div>

                <div className="object-list">
                  {multiObjectParams.objects.map((obj, index) => (
                    <div key={`${obj.name}_${index}`} className="object-card">
                      <div className="inline-actions">
                        <h4>Object {index + 1}</h4>
                        <button type="button" className="btn-generate" onClick={() => removeMultiObject(index)} disabled={multiObjectParams.objects.length === 1}>Remove</button>
                      </div>
                      <div className="param-grid">
                        <div className="param-group"><label>Name</label><input type="text" value={obj.name} onChange={(e) => updateMultiObject(index, { name: e.target.value })} /></div>
                        <div className="param-group checkbox-row"><label><input type="checkbox" checked={obj.enabled} onChange={(e) => updateMultiObject(index, { enabled: e.target.checked })} /> Enabled</label></div>
                        <div className="param-group"><label>Start Range (m)</label><input type="number" min="0" step="1" value={obj.start_range_m} onChange={(e) => updateMultiObject(index, { start_range_m: parseFloat(e.target.value) || 0 })} /></div>
                        <div className="param-group"><label>Stop Range (m)</label><input type="number" min="0" step="1" value={obj.stop_range_m} onChange={(e) => updateMultiObject(index, { stop_range_m: parseFloat(e.target.value) || 0 })} /></div>
                        <div className="param-group"><label>Radial Velocity (m/s)</label><input type="number" step="0.1" value={obj.radial_velocity_mps} onChange={(e) => updateMultiObject(index, { radial_velocity_mps: parseFloat(e.target.value) || 0 })} /></div>
                        <div className="param-group"><label>RCS (dBsm)</label><input type="number" step="1" value={obj.rcs_dbsm} onChange={(e) => updateMultiObject(index, { rcs_dbsm: parseFloat(e.target.value) || 0 })} /></div>
                        <div className="param-group"><label>Azimuth (deg)</label><input type="number" min="-180" max="360" step="1" value={obj.azimuth_deg} onChange={(e) => updateMultiObject(index, { azimuth_deg: parseFloat(e.target.value) || 0 })} /></div>
                        <div className="param-group"><label>Elevation (deg)</label><input type="number" min="-90" max="90" step="1" value={obj.elevation_deg} onChange={(e) => updateMultiObject(index, { elevation_deg: parseFloat(e.target.value) || 0 })} /></div>
                      </div>
                    </div>
                  ))}
                </div>

                <button className="btn-generate" onClick={onGenerateMultiObject} disabled={isGenerating}>Generate Multi-Object</button>
              </>
            )}

            {selectedTemplate === "azimuth_sweep" && (
              <>
                <h3>Azimuth Sweep Parameters</h3>
                <div className="param-grid">
                  <div className="param-group"><label>Sensor ID</label><input type="number" min="1" value={azimuthSweepParams.sensor_id} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, sensor_id: parseInt(e.target.value, 10) || 1 })} /></div>
                  <div className="param-group"><label>Duration (s)</label><input type="number" min="0.1" step="0.1" value={azimuthSweepParams.duration_s} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, duration_s: parseFloat(e.target.value) || 0.1 })} /></div>
                  <div className="param-group"><label>Update Interval (s)</label><input type="number" min="0.01" step="0.01" value={azimuthSweepParams.update_interval_s} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, update_interval_s: parseFloat(e.target.value) || 0.01 })} /></div>
                  <div className="param-group"><label>Range (m)</label><input type="number" min="0" step="1" value={azimuthSweepParams.range_m} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, range_m: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Start Azimuth (deg)</label><input type="number" min="-180" max="360" step="1" value={azimuthSweepParams.start_azimuth_deg} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, start_azimuth_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Stop Azimuth (deg)</label><input type="number" min="-180" max="360" step="1" value={azimuthSweepParams.stop_azimuth_deg} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, stop_azimuth_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Radial Velocity (m/s)</label><input type="number" step="0.1" value={azimuthSweepParams.radial_velocity_mps} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, radial_velocity_mps: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>RCS (dBsm)</label><input type="number" step="1" value={azimuthSweepParams.rcs_dbsm} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, rcs_dbsm: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Elevation (deg)</label><input type="number" min="-90" max="90" step="1" value={azimuthSweepParams.elevation_deg} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, elevation_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Output Directory</label><input type="text" value={azimuthSweepParams.output_dir} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, output_dir: e.target.value })} /></div>
                  <div className="param-group"><label>Output Filename</label><input type="text" value={azimuthSweepParams.output_filename} onChange={(e) => setAzimuthSweepParams({ ...azimuthSweepParams, output_filename: e.target.value })} /></div>
                </div>
                <button className="btn-generate" onClick={onGenerateAzimuthSweep} disabled={isGenerating}>Generate Azimuth Sweep</button>
              </>
            )}

            {selectedTemplate === "constant_echo_power" && (
              <>
                <h3>Constant Echo Power Parameters</h3>
                <p className="description">
                  RCS is adjusted per frame so the received echo power remains constant: RCS(R) = ref_rcs + 40·log₁₀(R / Rₐảỳ).
                </p>
                <div className="param-grid">
                  <div className="param-group"><label>Sensor ID</label><input type="number" min="1" value={constEchoPowerParams.sensor_id} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, sensor_id: parseInt(e.target.value, 10) || 1 })} /></div>
                  <div className="param-group"><label>Update Interval (s)</label><input type="number" min="0.01" step="0.01" value={constEchoPowerParams.update_interval_s} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, update_interval_s: parseFloat(e.target.value) || 0.01 })} /></div>
                  <div className="param-group"><label>Start Range (m)</label><input type="number" min="0.1" step="1" value={constEchoPowerParams.start_range_m} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, start_range_m: parseFloat(e.target.value) || 1 })} /></div>
                  <div className="param-group"><label>Stop Range (m)</label><input type="number" min="0.1" step="1" value={constEchoPowerParams.stop_range_m} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, stop_range_m: parseFloat(e.target.value) || 1 })} /></div>
                  <div className="param-group"><label>Radial Velocity (m/s)</label><input type="number" step="0.1" value={constEchoPowerParams.radial_velocity_mps} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, radial_velocity_mps: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Reference RCS (dBsm)</label><input type="number" step="1" value={constEchoPowerParams.ref_rcs_dbsm} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, ref_rcs_dbsm: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Reference Range (m)</label><input type="number" min="0.1" step="1" value={constEchoPowerParams.ref_range_m} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, ref_range_m: parseFloat(e.target.value) || 1 })} /></div>
                  <div className="param-group"><label>Azimuth (deg)</label><input type="number" min="-180" max="360" step="1" value={constEchoPowerParams.azimuth_deg} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, azimuth_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>Elevation (deg)</label><input type="number" min="-90" max="90" step="1" value={constEchoPowerParams.elevation_deg} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, elevation_deg: parseFloat(e.target.value) || 0 })} /></div>
                  <div className="param-group"><label>RCS Min Clamp (dBsm)</label><input type="number" step="1" value={constEchoPowerParams.rcs_min_dbsm} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, rcs_min_dbsm: parseFloat(e.target.value) || -30 })} /></div>
                  <div className="param-group"><label>RCS Max Clamp (dBsm)</label><input type="number" step="1" value={constEchoPowerParams.rcs_max_dbsm} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, rcs_max_dbsm: parseFloat(e.target.value) || 60 })} /></div>
                  <div className="param-group"><label>Output Directory</label><input type="text" value={constEchoPowerParams.output_dir} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, output_dir: e.target.value })} /></div>
                  <div className="param-group"><label>Output Filename</label><input type="text" value={constEchoPowerParams.output_filename} onChange={(e) => setConstEchoPowerParams({ ...constEchoPowerParams, output_filename: e.target.value })} /></div>
                </div>
                <button className="btn-generate" onClick={onGenerateConstantEchoPower} disabled={isGenerating}>Generate Constant Echo Power</button>
              </>
            )}
          </div>
        </details>

        <details className="sg-dropdown" open>
          <summary>Preview</summary>
          <div className="sg-dropdown-content">
            {lastPreview ? (
              <div className="preview-box">
                <div className="preview-row"><span>Duration</span><strong>{lastPreview.duration_s.toFixed(2)} s</strong></div>
                <div className="preview-row"><span>Messages</span><strong>{lastPreview.message_count}</strong></div>
                <div className="preview-row"><span>Objects</span><strong>{lastPreview.object_count}</strong></div>
                <div className="preview-row"><span>Range</span><strong>{lastPreview.min_range_m.toFixed(1)} - {lastPreview.max_range_m.toFixed(1)} m</strong></div>
                <div className="preview-row"><span>File Size</span><strong>{(lastPreview.estimated_file_size_bytes / 1024).toFixed(1)} KB</strong></div>
                {lastPreview.warnings.length > 0 && (
                  <div className="warnings">
                    <h4>Warnings</h4>
                    <ul>{lastPreview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="description">No preview yet. Generate a scenario to view metadata.</p>
            )}
            {generationResult?.rcs_table && generationResult.rcs_table.length > 0 && (
              <div className="rcs-table-section">
                <h4>RCS Compensation Table (sampled)</h4>
                <table className="rcs-table">
                  <thead><tr><th>Range (m)</th><th>Compensated RCS (dBsm)</th></tr></thead>
                  <tbody>
                    {generationResult.rcs_table.map((row, i) => (
                      <tr key={i}><td>{row.range_m.toFixed(1)}</td><td>{row.rcs_dbsm.toFixed(2)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </details>

        <details className="sg-dropdown" open>
          <summary>Result</summary>
          <div className="sg-dropdown-content">
            {isGenerating && (
              <div className="generating-indicator">
                <div className="spinner"></div>
                <p>Generating scenario...</p>
              </div>
            )}

            {generationResult && (
              <div className={`result-box ${generationResult.ok ? "success" : "error"}`}>
                {generationResult.ok ? (
                  <>
                    <h3>Generated Successfully</h3>
                    <p><strong>File:</strong> {generationResult.file_path}</p>
                    <p><strong>Messages:</strong> {generationResult.message_count}</p>
                    <p><strong>Duration:</strong> {generationResult.duration_s.toFixed(2)} s</p>
                  </>
                ) : (
                  <>
                    <h3>Generation Failed</h3>
                    <p><strong>Error:</strong> {generationResult.error}</p>
                  </>
                )}
              </div>
            )}

            {autoUploadStatus && (
              <div className={`result-box ${autoUploadStatus.ok ? "success" : "error"}`}>
                <h3>{autoUploadStatus.ok ? "Device Upload" : "Device Upload Warning"}</h3>
                <p>{autoUploadStatus.text}</p>
                {selectedUploadDirectory && (
                  <div className="sg-auto-indicator">
                    Auto-selected upload directory: {selectedUploadDirectory}
                  </div>
                )}
              </div>
            )}

            {!isGenerating && !generationResult && (
              <p className="description">No generation result yet.</p>
            )}
          </div>
        </details>
      </div>
    </div>
  );
}
