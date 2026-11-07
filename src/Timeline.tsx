import { useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { CURRENT_YEAR, timelineYears, yearCoverage, type CoverageLayer } from './timeline';
export default function Timeline({year,onChange,layers}:{year:number;onChange:(year:number)=>void;layers:CoverageLayer[]}) {
  const years=timelineYears(layers,year);
  const selected=useRef<HTMLButtonElement>(null);
  const coverage=yearCoverage(layers,year);
  useEffect(()=>{selected.current?.scrollIntoView({block:'nearest',inline:'center'});},[year,years[0]]);
  useEffect(()=>{
    const rail=selected.current?.parentElement;
    if(!rail)return;
    const observer=new ResizeObserver(()=>selected.current?.scrollIntoView({block:'nearest',inline:'center'}));
    observer.observe(rail);
    return ()=>observer.disconnect();
  },[]);
  return <section className="timeline shared-timeline" aria-label="Map year">
    <div className="timeline-label"><span className="eyebrow">MAP YEAR</span><strong>{year}</strong></div>
    <div className="timeline-navigation"><button className="year-arrow" aria-label="Previous year" disabled={year===years[0]} onClick={()=>onChange(year-1)}><ChevronLeft size={18}/></button>
      <div className="year-selector">{years.map(y=>{const c=yearCoverage(layers,y);return <button ref={y===year?selected:undefined} key={y} className={`year coverage-${c.state} ${year===y?'chosen':''}`} aria-pressed={year===y} aria-label={String(y)} title={`${y}: ${c.available}/${layers.length} layers available${c.missing.length?' · Missing: '+c.missing.map(l=>l.title).join(', '):''}`} onClick={()=>onChange(y)}><span className="year-dot"/>{y}</button>;})}</div>
      <button className="year-arrow" aria-label="Next year" disabled={year===CURRENT_YEAR} onClick={()=>onChange(year+1)}><ChevronRight size={18}/></button></div>
    <div className="timeline-coverage"><span role="status">{layers.length?`${coverage.available} of ${layers.length} active layers cover ${year}`:'Turn on layers to see year coverage'}</span><div className="coverage-key"><span><i className="full"/>All</span><span><i className="partial"/>Some</span><span><i className="none"/>None</span><span>Current / undated = {CURRENT_YEAR}</span></div>{coverage.missing.length>0&&<details><summary>Missing for {year} ({coverage.missing.length})</summary><ul>{coverage.missing.map(l=><li key={l.id}>{l.title}</li>)}</ul><p>These layers stay enabled but are hidden from this year’s map.</p></details>}</div>
  </section>;
}
