import React, { useState, useEffect, useCallback } from 'react';
import { analysisApi, type ScoringConfig } from '../services/api';
import { Settings, RotateCcw } from 'lucide-react';

interface ScoringConfigPanelProps {
    onConfigChange?: (config: ScoringConfig) => void;
}

const INTERVALS = ['1h', '2h', '3h', '4h', '1d'] as const;

const WeightSliderGroup: React.FC<{
    label: string;
    weights: { divergence: number; price_position: number; volume: number };
    onChange: (weights: { divergence: number; price_position: number; volume: number }) => void;
}> = ({ label, weights, onChange }) => {
    const total = weights.divergence + weights.price_position + weights.volume;

    const handleChange = (key: 'divergence' | 'price_position' | 'volume', value: number) => {
        onChange({ ...weights, [key]: value });
    };

    return (
        <div className="mb-4">
            <div className="text-sm font-medium mb-2 flex items-center gap-2">
                {label}
                <span className={`text-xs font-normal ${total === 100 ? 'text-green-500' : 'text-red-500'}`}>
                    (Total: {total})
                </span>
            </div>
            {([
                ['divergence', 'Divergence'],
                ['price_position', 'Price Position'],
                ['volume', 'Volume']
            ] as const).map(([key, name]) => (
                <div key={key} className="flex items-center gap-3 mb-1.5">
                    <span className="w-24 text-xs text-muted-foreground">{name}</span>
                    <input
                        type="range"
                        min={0} max={100} step={5}
                        value={weights[key]}
                        onChange={e => handleChange(key, Number(e.target.value))}
                        className="flex-1 accent-primary h-1.5"
                    />
                    <input
                        type="number"
                        min={0} max={100} step={5}
                        value={weights[key]}
                        onChange={e => handleChange(key, Number(e.target.value))}
                        className="w-14 text-center text-xs bg-background border border-input rounded px-1 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                </div>
            ))}
        </div>
    );
};

const ScoringConfigPanel: React.FC<ScoringConfigPanelProps> = ({ onConfigChange }) => {
    const [config, setConfig] = useState<ScoringConfig | null>(null);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);

    useEffect(() => {
        analysisApi.getScoringConfig().then(setConfig).catch(console.error);
    }, []);

    const updateField = useCallback((field: keyof ScoringConfig, value: any) => {
        setConfig(prev => prev ? { ...prev, [field]: value } : prev);
        setDirty(true);
    }, []);

    const handleSave = useCallback(async () => {
        if (!config) return;
        setSaving(true);
        try {
            const updated = await analysisApi.updateScoringConfig(config);
            setConfig(updated);
            setDirty(false);
            onConfigChange?.(updated);
        } catch (e) {
            console.error('Failed to save scoring config:', e);
        } finally {
            setSaving(false);
        }
    }, [config, onConfigChange]);

    const handleReset = useCallback(async () => {
        if (!confirm('Reset all weights to default values?')) return;
        try {
            const defaults = await analysisApi.getScoringConfigDefaults();
            setConfig(defaults);
            setDirty(true);
        } catch (e) {
            console.error('Failed to load defaults:', e);
        }
    }, []);

    if (!config) return null;

    return (
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border bg-muted/30 flex justify-between items-center">
                <h3 className="font-semibold flex items-center gap-2">
                    <Settings className="w-4 h-4" /> Scoring Weights
                </h3>
            </div>

            <div className="p-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* CD Component Weights */}
                    <WeightSliderGroup
                        label="CD (Buy) Component Weights"
                        weights={config.cd_component_weights}
                        onChange={w => updateField('cd_component_weights', w)}
                    />

                    {/* MC Component Weights */}
                    <WeightSliderGroup
                        label="MC (Sell) Component Weights"
                        weights={config.mc_component_weights}
                        onChange={w => updateField('mc_component_weights', w)}
                    />
                </div>

                {/* Interval Multipliers */}
                <div className="mt-2 mb-4">
                    <div className="text-sm font-medium mb-2">Interval Multipliers</div>
                    <div className="flex gap-4 flex-wrap">
                        {INTERVALS.map(intv => (
                            <div key={intv} className="flex items-center gap-2">
                                <span className="text-xs text-muted-foreground w-6">{intv}</span>
                                <input
                                    type="number"
                                    min={0} max={100} step={1}
                                    value={config.interval_weights[intv]}
                                    onChange={e => updateField('interval_weights', {
                                        ...config.interval_weights,
                                        [intv]: Number(e.target.value)
                                    })}
                                    className="w-14 text-center text-xs bg-background border border-input rounded px-1 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
                                />
                            </div>
                        ))}
                    </div>
                </div>

                {/* Score Thresholds */}
                <div className="mt-2 mb-4">
                    <div className="text-sm font-medium mb-2">Score Thresholds
                        <span className="text-xs font-normal text-muted-foreground ml-2">
                            (signals below threshold are ignored)
                        </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="flex items-center gap-3">
                            <span className="w-24 text-xs text-muted-foreground">CD (Buy)</span>
                            <input
                                type="range"
                                min={0} max={100} step={5}
                                value={config.cd_threshold}
                                onChange={e => updateField('cd_threshold', Number(e.target.value))}
                                className="flex-1 accent-primary h-1.5"
                            />
                            <input
                                type="number"
                                min={0} max={100} step={5}
                                value={config.cd_threshold}
                                onChange={e => updateField('cd_threshold', Number(e.target.value))}
                                className="w-14 text-center text-xs bg-background border border-input rounded px-1 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="w-24 text-xs text-muted-foreground">MC (Sell)</span>
                            <input
                                type="range"
                                min={0} max={100} step={5}
                                value={config.mc_threshold}
                                onChange={e => updateField('mc_threshold', Number(e.target.value))}
                                className="flex-1 accent-primary h-1.5"
                            />
                            <input
                                type="number"
                                min={0} max={100} step={5}
                                value={config.mc_threshold}
                                onChange={e => updateField('mc_threshold', Number(e.target.value))}
                                className="w-14 text-center text-xs bg-background border border-input rounded px-1 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={handleSave}
                        disabled={saving || !dirty}
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-2 ${dirty
                            ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                            : 'bg-muted text-muted-foreground cursor-default'
                            }`}
                    >
                        {saving ? 'Saving...' : dirty ? 'Save & Apply' : 'Saved ✓'}
                    </button>

                    <button
                        onClick={handleReset}
                        className="px-4 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-muted transition-colors flex items-center gap-2 border border-transparent hover:border-border"
                        title="Reset to Defaults"
                    >
                        <RotateCcw className="w-4 h-4" />
                        Reset Defaults
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ScoringConfigPanel;
