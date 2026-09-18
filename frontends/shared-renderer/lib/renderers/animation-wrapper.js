"use client";
import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { motion, useSpring, useTransform } from "framer-motion";
/** CSS-based animated gradient border (Magic UI border-beam equivalent). */
function BorderBeamWrapper({ children }) {
    return (_jsxs("div", { className: "relative rounded-lg", children: [_jsx("div", { className: "pointer-events-none absolute -inset-px rounded-lg", style: {
                    background: "linear-gradient(var(--border-beam-angle, 0deg), transparent 40%, hsl(var(--primary)) 50%, transparent 60%)",
                    animation: "border-beam-spin 4s linear infinite",
                    mask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
                    maskComposite: "exclude",
                    WebkitMaskComposite: "xor",
                    padding: "1.5px",
                } }), children, _jsx("style", { children: `
        @keyframes border-beam-spin {
          from { --border-beam-angle: 0deg; }
          to { --border-beam-angle: 360deg; }
        }
        @property --border-beam-angle {
          syntax: "<angle>";
          initial-value: 0deg;
          inherits: false;
        }
      ` })] }));
}
/** Animated number counting up (Magic UI number-ticker equivalent). */
function NumberTickerWrapper({ children }) {
    const ref = useRef(null);
    const [target, setTarget] = useState(0);
    useEffect(() => {
        const text = ref.current?.textContent ?? "";
        const num = parseFloat(text.replace(/[^0-9.-]/g, ""));
        if (!isNaN(num))
            setTarget(num);
    }, []);
    const spring = useSpring(0, { stiffness: 50, damping: 20 });
    const display = useTransform(spring, (v) => Math.round(v).toLocaleString());
    useEffect(() => {
        spring.set(target);
    }, [target, spring]);
    return (_jsxs("div", { ref: ref, children: [_jsx("span", { className: "sr-only", children: children }), _jsx(motion.span, { "aria-hidden": true, children: display })] }));
}
/** CSS shimmer/shine on hover (Magic UI shimmer equivalent). */
function ShimmerWrapper({ children }) {
    return (_jsxs("div", { className: "group relative overflow-hidden", children: [children, _jsx("div", { className: "pointer-events-none absolute inset-0 -translate-x-full group-hover:animate-shimmer", style: {
                    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)",
                } }), _jsx("style", { children: `
        @keyframes shimmer {
          to { transform: translateX(100%); }
        }
        .group:hover .animate-shimmer {
          animation: shimmer 0.75s ease-in-out;
        }
      ` })] }));
}
/** Text fade-in word by word (Magic UI text-reveal equivalent). */
function TextRevealWrapper({ children }) {
    const ref = useRef(null);
    const [words, setWords] = useState([]);
    useEffect(() => {
        const text = ref.current?.textContent ?? "";
        if (text)
            setWords(text.split(/\s+/));
    }, []);
    if (words.length === 0) {
        return _jsx("div", { ref: ref, children: children });
    }
    return (_jsxs("div", { ref: ref, children: [_jsx("span", { className: "sr-only", children: children }), _jsx("span", { "aria-hidden": true, children: words.map((word, i) => (_jsx(motion.span, { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { delay: i * 0.06, duration: 0.3 }, className: "inline-block mr-1", children: word }, i))) })] }));
}
/** Framer-motion fade-in (opacity 0→1). */
function FadeInWrapper({ children }) {
    return (_jsx(motion.div, { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.5 }, children: children }));
}
/** Framer-motion slide-in (opacity 0→1 + translateY 20→0). */
function SlideInWrapper({ children }) {
    return (_jsx(motion.div, { initial: { opacity: 0, y: 20 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.4, ease: "easeOut" }, children: children }));
}
const EFFECT_MAP = {
    "border-beam": BorderBeamWrapper,
    "number-ticker": NumberTickerWrapper,
    shimmer: ShimmerWrapper,
    "text-reveal": TextRevealWrapper,
    "fade-in": FadeInWrapper,
    "slide-in": SlideInWrapper,
};
export function AnimationWrapper({ animation, children }) {
    const Wrapper = EFFECT_MAP[animation.effect];
    if (!Wrapper)
        return _jsx(_Fragment, { children: children });
    return _jsx(Wrapper, { children: children });
}
