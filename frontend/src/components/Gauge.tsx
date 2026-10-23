import React from 'react';
import { cn } from '../utils/cn';

// Semicircle gauge in the style of a fear & greed index: 0 on the left, 100 on the right.

export interface GaugeZone { to: number; label: string; tone: 'sell-strong' | 'sell' | 'neutral' | 'buy' | 'buy-strong' | 'plain' }

/** Zones for a CD (buy) vs MC (sell) balance: low = MC dominates, high = CD dominates. */
export const BALANCE_ZONES: GaugeZone[] = [
    { to: 20, label: 'Strong MC', tone: 'sell-strong' },
    { to: 40, label: 'MC', tone: 'sell' },
    { to: 60, label: 'Neutral', tone: 'neutral' },
    { to: 80, label: 'CD', tone: 'buy' },
    { to: 100, label: 'Strong CD', tone: 'buy-strong' },
];

export const PLAIN_ZONES: GaugeZone[] = [
    { to: 25, label: 'Low', tone: 'plain' },
    { to: 75, label: 'Normal', tone: 'plain' },
    { to: 100, label: 'High', tone: 'plain' },
];

const TONE_ACTIVE: Record<GaugeZone['tone'], string> = {
    'sell-strong': 'fill-red-500/70 stroke-red-600',
    'sell': 'fill-red-400/40 stroke-red-500',
    'neutral': 'fill-muted-foreground/30 stroke-muted-foreground',
    'buy': 'fill-green-400/40 stroke-green-500',
    'buy-strong': 'fill-green-500/70 stroke-green-600',
    'plain': 'fill-blue-500/40 stroke-blue-500',
};

const TONE_TEXT: Record<GaugeZone['tone'], string> = {
    'sell-strong': 'text-red-500',
    'sell': 'text-red-400',
    'neutral': 'text-muted-foreground',
    'buy': 'text-green-500',
    'buy-strong': 'text-green-500',
    'plain': 'text-blue-500',
};

export const zoneOf = (value: number, zones: GaugeZone[]) => zones.find(z => value <= z.to) ?? zones[zones.length - 1];
export const toneText = (zone: GaugeZone) => TONE_TEXT[zone.tone];

// Point on the arc: value 0..100 maps to 180°..0° (left to right over the top)
const polar = (cx: number, cy: number, r: number, value: number) => {
    const a = Math.PI * (1 - value / 100);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
};

const sector = (cx: number, cy: number, r0: number, r1: number, from: number, to: number) => {
    const [x0, y0] = polar(cx, cy, r1, from);
    const [x1, y1] = polar(cx, cy, r1, to);
    const [x2, y2] = polar(cx, cy, r0, to);
    const [x3, y3] = polar(cx, cy, r0, from);
    return `M ${x0} ${y0} A ${r1} ${r1} 0 0 1 ${x1} ${y1} L ${x2} ${y2} A ${r0} ${r0} 0 0 0 ${x3} ${y3} Z`;
};

export const Gauge: React.FC<{
    value: number;           // 0..100
    zones?: GaugeZone[];
    size?: 'lg' | 'sm';
    title?: string;
    caption?: React.ReactNode;
}> = ({ value, zones = BALANCE_ZONES, size = 'sm', title, caption }) => {
    const v = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 50));
    const W = 200, H = 106, cx = 100, cy = 102, r1 = 96, r0 = size === 'lg' ? 62 : 66;
    const hub = size === 'lg' ? 34 : 40;  // centre disc holding the number
    const active = zoneOf(v, zones);
    const [bx, by] = polar(cx, cy, hub, v);
    const [nx, ny] = polar(cx, cy, r0 + (r1 - r0) * 0.45, v);
    let from = 0;
    return (
        <div className="flex flex-col items-center min-w-0">
            {title && <div className={cn("font-medium text-muted-foreground", size === 'lg' ? 'text-xs mb-1' : 'text-[10px]')}>{title}</div>}
            <svg viewBox={`0 0 ${W} ${H}`} className={size === 'lg' ? 'w-full max-w-[210px]' : 'w-full max-w-[96px]'}>
                {zones.map(z => {
                    const d = sector(cx, cy, r0, r1, from + 0.6, z.to - 0.6);
                    const isActive = z === active;
                    from = z.to;
                    return <path key={z.to} d={d}
                        className={isActive ? TONE_ACTIVE[z.tone] : 'fill-muted stroke-transparent'}
                        strokeWidth={isActive ? 1.5 : 0} />;
                })}
                {size === 'lg' && zones.map((z, i) => {
                    const start = i === 0 ? 0 : zones[i - 1].to;
                    const [tx, ty] = polar(cx, cy, (r0 + r1) / 2, (start + z.to) / 2);
                    return <text key={`t${z.to}`} x={tx} y={ty} textAnchor="middle" dominantBaseline="middle"
                        className="fill-muted-foreground" style={{ fontSize: 9, fontWeight: 600 }}>{z.label}</text>;
                })}
                <line x1={bx} y1={by} x2={nx} y2={ny} className="stroke-foreground" strokeWidth={size === 'lg' ? 4 : 6} strokeLinecap="round" />
                <circle cx={cx} cy={cy} r={hub} className="fill-card stroke-border" strokeWidth={1} />
                <text x={cx} y={cy - 6} textAnchor="middle" className="fill-foreground"
                    style={{ fontSize: size === 'lg' ? 26 : 30, fontWeight: 700 }}>{Math.round(v)}</text>
            </svg>
            <div className={cn("font-semibold leading-tight", toneText(active), size === 'lg' ? 'text-sm' : 'text-[10px]')}>{active.label}</div>
            {caption && <div className="text-[10px] text-muted-foreground text-center leading-tight mt-0.5">{caption}</div>}
        </div>
    );
};
