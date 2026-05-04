import { useEffect, useMemo, useState } from "react";

type CommandTemplate = {
  group: string;
  command: string;
  purpose: string;
  example?: string | null;
  placeholders: string[];
};

type CommandLibrary = {
  device: string;
  warning: string;
  placeholders: Record<string, string>;
  commands: CommandTemplate[];
};

type CommandBuilderProps = {
  command: string;
  onCommandChange: (value: string) => void;
};

const API_BASE = "http://127.0.0.1:8000/api";

function defaultPlaceholderValue(name: string): string {
  const normalized = name.trim().toLowerCase();
  if (["hw", "ch", "st", "di"].includes(normalized)) {
    return "1";
  }
  if (normalized.includes("bool") || normalized.includes("on|off") || normalized === "state") {
    return "ON";
  }
  return "";
}

function normalizeTemplate(template: string): string {
  return template
    .replace(/\[:([^\]|]+)\|([^\]]+)\]/g, ":$1")
    .replace(/\[:([^\]]+)\]/g, ":$1");
}

function buildCommand(template: string, values: Record<string, string>): string {
  const normalizedTemplate = normalizeTemplate(template);
  return normalizedTemplate.replace(/<([^>]+)>/g, (_match, rawName: string) => values[rawName.trim()] ?? `<${rawName}>`);
}

export default function CommandBuilder({ command, onCommandChange }: CommandBuilderProps) {
  const [library, setLibrary] = useState<CommandLibrary | null>(null);
  const [selectedCommand, setSelectedCommand] = useState<string>("");
  const [placeholderValues, setPlaceholderValues] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadLibrary = async () => {
      setStatus("loading");
      setError(null);
      try {
        const response = await fetch(`${API_BASE}/areg/library`);
        if (!response.ok) {
          const payload = (await response.json()) as { detail?: string };
          throw new Error(payload.detail ?? "Failed to load command library");
        }

        const payload = (await response.json()) as CommandLibrary;
        if (cancelled) {
          return;
        }

        setLibrary(payload);
        const firstCommand = payload.commands[0];
        if (firstCommand) {
          setSelectedCommand(firstCommand.command);
          const initialValues = Object.fromEntries(
            firstCommand.placeholders.map((placeholder) => [placeholder, defaultPlaceholderValue(placeholder)])
          );
          setPlaceholderValues(initialValues);
          onCommandChange(buildCommand(firstCommand.command, initialValues));
        }
        setStatus("ready");
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        setStatus("error");
        setError(loadError instanceof Error ? loadError.message : "Unknown error");
      }
    };

    void loadLibrary();

    return () => {
      cancelled = true;
    };
  }, [onCommandChange]);

  const selectedTemplate = useMemo(
    () => library?.commands.find((entry) => entry.command === selectedCommand) ?? null,
    [library, selectedCommand]
  );

  useEffect(() => {
    if (!selectedTemplate) {
      return;
    }

    const nextValues = Object.fromEntries(
      selectedTemplate.placeholders.map((placeholder) => [placeholder, defaultPlaceholderValue(placeholder)])
    );
    setPlaceholderValues(nextValues);
    onCommandChange(buildCommand(selectedTemplate.command, nextValues));
  }, [onCommandChange, selectedTemplate]);

  const updatePlaceholder = (placeholder: string, value: string) => {
    setPlaceholderValues((current) => {
      const nextValues = { ...current, [placeholder]: value };
      if (selectedTemplate) {
        onCommandChange(buildCommand(selectedTemplate.command, nextValues));
      }
      return nextValues;
    });
  };

  const selectCommand = (nextCommand: string) => {
    setSelectedCommand(nextCommand);
    const template = library?.commands.find((entry) => entry.command === nextCommand);
    if (!template) {
      return;
    }

    const nextValues = Object.fromEntries(
      template.placeholders.map((placeholder) => [placeholder, defaultPlaceholderValue(placeholder)])
    );
    setPlaceholderValues(nextValues);
    onCommandChange(buildCommand(template.command, nextValues));
  };

  return (
    <div className="command-builder">
      <div className="builder-head">
        <div>
          <strong>Command Picker</strong>
          <p className="muted small">
            Choose a command template, fill in the placeholders, then send the generated SCPI line.
          </p>
        </div>
        {library && <span className="builder-meta">{library.device}</span>}
      </div>

      {library && library.warning && <p className="warning-box">{library.warning}</p>}
      {error && <p className="error">{error}</p>}

      <div className="builder-grid">
        <label>
          Command template
          <select value={selectedCommand} onChange={(e) => selectCommand(e.target.value)} disabled={status !== "ready"}>
            {library?.commands.map((entry) => (
              <option key={`${entry.group}:${entry.command}`} value={entry.command}>
                {entry.group} · {entry.command}
              </option>
            ))}
          </select>
        </label>

        {selectedTemplate && selectedTemplate.placeholders.length > 0 && (
          <div className="placeholder-grid">
            {selectedTemplate.placeholders.map((placeholder) => (
              <label key={placeholder}>
                {library?.placeholders[placeholder] ?? placeholder}
                <input
                  value={placeholderValues[placeholder] ?? ""}
                  onChange={(e) => updatePlaceholder(placeholder, e.target.value)}
                  placeholder={defaultPlaceholderValue(placeholder) || placeholder}
                />
              </label>
            ))}
          </div>
        )}

        <label>
          Generated SCPI
          <textarea
            className="command-preview"
            value={command}
            onChange={(e) => onCommandChange(e.target.value)}
            rows={4}
          />
        </label>

        {selectedTemplate?.example && (
          <p className="muted small">Example: {selectedTemplate.example}</p>
        )}
      </div>
    </div>
  );
}