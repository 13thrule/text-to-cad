#!/usr/bin/env node
var br=Object.defineProperty;var p=(n,t)=>br(n,"name",{value:t,configurable:!0});var zn=(n,t)=>()=>(n&&(t=n(n=0)),t);var ja=(n,t)=>{for(var e in t)br(n,e,{get:t[e],enumerable:!0})};function wi(n,t,e){if(!n)return null;let i=n.userData.cadTubeShader;if(!i){let r=n.onBeforeCompile,o=n.customProgramCacheKey;i=n.userData.cadTubeShader={stages:{}},n.onBeforeCompile=function(a,c){r.call(this,a,c);for(let u of Qo){let h=i.stages[u];h&&(Object.assign(a.uniforms,h.uniforms),h.apply(a,i.stages))}let l=`#include <common>
varying vec3 ${ge};`;a.vertexShader=a.vertexShader.replace("#include <common>",l),a.fragmentShader=a.fragmentShader.replace("#include <common>",l)},n.customProgramCacheKey=function(){let a=Qo.filter(c=>i.stages[c]).join("+");return`${o.call(this)}:cad-tube:${a}`},n.needsUpdate=!0}let s=i.stages[t];return s||(s=i.stages[t]=e(),n.needsUpdate=!0),s}var ge,Pn,Ti,Qo,Ei=zn(()=>{ge="vCadTubeMaterial",Pn="cadTubeMaterial",Ti="braid",Qo=["gpu",Ti];p(wi,"ensureTubeMaterialStage")});function Cf(n,t){t["gpu"]||(n.vertexShader=n.vertexShader.replace("#include <common>",`#include <common>
attribute vec3 ${Pn};`).replace("#include <begin_vertex>",`#include <begin_vertex>
${ge} = ${Pn};`)),n.fragmentShader=n.fragmentShader.replace("#include <common>",`#include <common>
${Ef}`).replace("#include <color_fragment>",`#include <color_fragment>
float cadBraidRelief = cadBraidHeight();
diffuseColor.rgb *= 1.0 + 0.22 * cadBraidRelief / max(cadBraidParameters.y, 0.000001);`).replace("#include <normal_fragment_maps>",`#include <normal_fragment_maps>
if (cadBraidEnabled > 0.5) normal = cadBraidNormal(-vViewPosition, normal, cadBraidRelief);`)}function ta(n,t,e){if(!t||!e&&!t.userData.cadTubeShader?.stages[Ti])return;let i=wi(t,Ti,()=>({uniforms:{cadBraidParameters:{value:new n.Vector3(1,0,8)},cadBraidEnabled:{value:0}},apply:Cf}));i.uniforms.cadBraidEnabled.value=e?1:0,e&&i.uniforms.cadBraidParameters.value.set(e.pitch,e.depth,e.strands)}var Ef,ea=zn(()=>{Ei();Ef=`
uniform vec3 cadBraidParameters;
uniform float cadBraidEnabled;
float cadBraidHeight() {
  float angle = atan(${ge}.z, ${ge}.y);
  float turns = ${ge}.x / cadBraidParameters.x;
  float carrierA = cadBraidParameters.z * (angle / 6.28318530718 + turns);
  float carrierB = cadBraidParameters.z * (angle / 6.28318530718 - turns);
  float a = fract(carrierA), b = fract(carrierB);
  float bandA = sqrt(max(0.0, 1.0 - pow((a - 0.5) / 0.44, 2.0)));
  float bandB = sqrt(max(0.0, 1.0 - pow((b - 0.5) / 0.44, 2.0)));
  float over = mod(floor(carrierA) + floor(carrierB), 2.0);
  float crown = mix(max(bandA, bandB * 0.60), max(bandB, bandA * 0.60), over);
  float fineFibers = 0.035 * cos(6.28318530718 * 5.0 * mix(carrierA, carrierB, over));
  return cadBraidEnabled * cadBraidParameters.y * (crown + fineFibers - 1.035);
}
vec3 cadBraidNormal(vec3 surfacePosition, vec3 surfaceNormal, float height) {
  vec3 dx = dFdx(surfacePosition), dy = dFdy(surfacePosition);
  vec3 r1 = cross(dy, surfaceNormal), r2 = cross(surfaceNormal, dx);
  float determinant = dot(dx, r1);
  vec3 gradient = sign(determinant) * (dFdx(height) * r1 + dFdy(height) * r2);
  return normalize(abs(determinant) * surfaceNormal - gradient);
}
`;p(Cf,"applyBraidStage");p(ta,"applyTubeBraidMaterial")});function Nf(n,t){let e=[];for(let o of n.segments){let a=o.kind==="bezier"?o.table:null,c=a?.length??(o.kind==="line"?2:Math.ceil(o.length/o.radius/If)+1);for(let l=0;l<c;l++){let u=a?.[l],h=u?u.s:o.length*l/(c-1),f=o.offset+h,d=u?.curvature?u:t(n,f),m={s:f,point:d.point,tangent:d.tangent,normal:d.normal,curvature:d.curvature};e.length&&f<=e.at(-1).s+1e-12?e[e.length-1]=m:e.push(m)}}let i=Math.max(2,Math.ceil(n.length/Rf)+1),s=new Float32Array(i*16),r=0;for(let o=0;o<i;o++){let a=n.length*o/(i-1);for(;r<e.length-2&&e[r+1].s<a;)r++;let c=e[r],l=e[r+1],u=l.s-c.s,h=Math.max(0,Math.min(1,(a-c.s)/u)),f=1-h,d=2*h*h*h-3*h*h+1,m=h*h*h-2*h*h+h,g=-2*h*h*h+3*h*h,_=h*h*h-h*h,x=f*c.tangent[0]+h*l.tangent[0],v=f*c.tangent[1]+h*l.tangent[1],y=f*c.tangent[2]+h*l.tangent[2],b=Math.hypot(x,v,y);x/=b,v/=b,y/=b;let S=f*c.normal[0]+h*l.normal[0],A=f*c.normal[1]+h*l.normal[1],M=f*c.normal[2]+h*l.normal[2],T=S*x+A*v+M*y;S-=T*x,A-=T*v,M-=T*y;let I=Math.hypot(S,A,M);S/=I,A/=I,M/=I;let E=o*16;for(let N=0;N<3;N++)s[E+N]=d*c.point[N]+m*u*c.tangent[N]+g*l.point[N]+_*u*l.tangent[N],s[E+12+N]=f*c.curvature[N]+h*l.curvature[N];s.set([x,v,y],E+4),s.set([S,A,M],E+8)}return{data:s,count:i}}function Df(n){n.vertexShader=n.vertexShader.replace("#include <common>",`#include <common>
${Lf}`).replace("#include <beginnormal_vertex>",`#include <beginnormal_vertex>
cadEvaluateTube();
if (cadTubeGpuEnabled > 0.5) objectNormal = cadGpuNormal;`).replace("#include <begin_vertex>",`#include <begin_vertex>
cadEvaluateTube();
if (cadTubeGpuEnabled > 0.5) transformed = cadGpuPoint;
${ge} = cadTubeMaterialCoordinates();`)}function er(n,t){if(!n)return;let e=wi(n,"gpu",()=>({uniforms:t,apply:Df}));if(e.uniforms!==t)for(let[i,s]of Object.entries(t))e.uniforms[i]?e.uniforms[i].value=s.value:(e.uniforms[i]=s,n.needsUpdate=!0)}function ir(n){let t=n?.tubeGpuState;t&&(t.uniforms.cadTubeGpuEnabled.value=0,t.active=!1,n.mesh.userData.cadBeforeRaycast=null)}function sr(n){let t=n?.tubeGpuState;if(t?.active)for(let e of[n.mesh,n.silhouette,n.ghostMesh])e&&er(e.material,t.uniforms)}function Uf(n,t,e,i,s){let r=e.mapping,o=Pf,a=Math.ceil(r.values.length/4/o),c=r.values;r.gpu||(c=new Float32Array(o*a*4),c.set(r.values));let l=new n.DataTexture(c,o,a,n.RGBAFormat,n.FloatType);l.needsUpdate=!0;let u=r.gpu?r.indices:new Float32Array(r.indices);e.geometry.setAttribute("cadTubeMappingIndex",new n.BufferAttribute(u,1));let h=0;for(let f=0;f<r.values.length;f+=8)h=Math.max(h,Math.hypot(r.values[f+1],r.values[f+2],r.values[f+3]));return{mapping:r,mappingTexture:l,radius:h,active:!0,uniforms:{cadTubeMappingTexture:{value:l},cadTubeFrameTexture:{value:null},cadTubeMappingSize:{value:new n.Vector2(o,a)},cadTubeFrameCount:{value:0},cadTubeRestLength:{value:i.rest.length},cadTubeGpuEnabled:{value:1},cadTubeGpuParameters:{value:new n.Vector3},cadTubeGpuInverse:{value:s.clone()},cadTubeGpuNormalMatrix:{value:new n.Matrix3().getNormalMatrix(s)}}}}function Ff(n,t,e,i,s,r,o){let a=i.frames;t.mesh.userData.cadBeforeRaycast=c=>{if(!i.active)return!0;let l=c.ray.clone().applyMatrix4(t.mesh.matrixWorld.clone().invert());if(!l.intersectsBox(e.geometry.boundingBox))return!1;let u=l.clone().applyMatrix4(r.clone().invert()),h=new n.Vector3,f=new n.Vector3,d=Math.max(1,Math.floor((a.count-1)/s.path.length)),m=!1;for(let g=0;g<a.count-1;g+=d){let _=Math.min(g+d,a.count-1);h.fromArray(a.data,g*16),f.fromArray(a.data,_*16);let x=i.radius+(_-g)*s.path.length/(a.count-1)/2+1e-4;if(u.distanceSqToSegment(h,f)<=x*x){m=!0;break}}return m?(i.cpuSpec!==s.pathSpec&&(o(),i.cpuSpec=s.pathSpec),!0):!1}}function na(n,t,e,i,s,r,o){if(!t.gpuTubeDeformationAllowed||i.path.length>nr)return!1;let a=t.tubeGpuState;(!a||a.mapping!==e.mapping)&&(a?.mappingTexture.dispose(),a?.frameTexture?.dispose(),a=t.tubeGpuState=Uf(n,t,e,i,s)),a.cleanupInstalled||(e.geometry.addEventListener("dispose",()=>{a.mappingTexture.dispose(),a.frameTexture?.dispose()}),a.cleanupInstalled=!0);let c=Nf(i.path,r);!a.frameTexture||a.frameTexture.image.height!==c.count?(a.frameTexture?.dispose(),a.frameTexture=new n.DataTexture(c.data,4,c.count,n.RGBAFormat,n.FloatType)):a.frameTexture.image.data.set(c.data),a.frameTexture.needsUpdate=!0,a.frames=c,a.active=!0,a.cpuSpec=null;let l=a.uniforms;l.cadTubeFrameTexture.value=a.frameTexture,l.cadTubeFrameCount.value=c.count,l.cadTubeGpuEnabled.value=1,l.cadTubeGpuParameters.value.set(i.twistDeg*Math.PI/180,i.path.length/i.rest.length,0),l.cadTubeGpuInverse.value.copy(s),l.cadTubeGpuNormalMatrix.value.getNormalMatrix(s),sr(t),t.mesh.customDepthMaterial||(t.mesh.customDepthMaterial=new n.MeshDepthMaterial({depthPacking:n.RGBADepthPacking}),t.mesh.customDistanceMaterial=new n.MeshDistanceMaterial,t.mesh.material.addEventListener("dispose",()=>{t.mesh.customDepthMaterial?.dispose(),t.mesh.customDistanceMaterial?.dispose()})),er(t.mesh.customDepthMaterial,l),er(t.mesh.customDistanceMaterial,l);let u=new n.Box3;for(let h of i.path.segments)u.expandByPoint(new n.Vector3().fromArray(h.bounds.min)),u.expandByPoint(new n.Vector3().fromArray(h.bounds.max));return u.expandByScalar(a.radius+1e-4),t.partBounds={min:u.min.toArray(),max:u.max.toArray()},e.geometry.boundingBox=u.clone().applyMatrix4(s),e.geometry.boundingSphere=e.geometry.boundingBox.getBoundingSphere(new n.Sphere),Ff(n,t,e,a,i,s,o),!0}var nr,Rf,If,Pf,Lf,ia=zn(()=>{Ei();nr=819.1,Rf=.1,If=.01,Pf=1024;p(Nf,"buildGpuTubeFrames");Lf=`
attribute float cadTubeMappingIndex;
uniform sampler2D cadTubeMappingTexture;
uniform sampler2D cadTubeFrameTexture;
uniform vec2 cadTubeMappingSize;
uniform float cadTubeFrameCount;
uniform float cadTubeRestLength;
uniform float cadTubeGpuEnabled;
uniform vec3 cadTubeGpuParameters;
uniform mat4 cadTubeGpuInverse;
uniform mat3 cadTubeGpuNormalMatrix;
vec3 cadGpuPoint;
vec3 cadGpuNormal;
bool cadGpuEvaluated = false;
vec4 cadMapping(float index) {
  vec2 texel = vec2(mod(index, cadTubeMappingSize.x), floor(index / cadTubeMappingSize.x));
  return texture2D(cadTubeMappingTexture, (texel + 0.5) / cadTubeMappingSize);
}
vec3 cadFrame(float row, float column) {
  return texture2D(cadTubeFrameTexture, vec2((column + 0.5) / 4.0, (row + 0.5) / cadTubeFrameCount)).xyz;
}
vec3 cadTubeMaterialCoordinates() {
  vec4 a = cadMapping(2.0 * cadTubeMappingIndex);
  return vec3(a.x * cadTubeRestLength, a.yz);
}
void cadEvaluateTube() {
  if (cadGpuEvaluated || cadTubeGpuEnabled < 0.5) return;
  cadGpuEvaluated = true;
  vec4 a = cadMapping(2.0 * cadTubeMappingIndex);
  vec4 b = cadMapping(2.0 * cadTubeMappingIndex + 1.0);
  float f = clamp(a.x, 0.0, 1.0) * (cadTubeFrameCount - 1.0);
  float lo = floor(f);
  float hi = min(lo + 1.0, cadTubeFrameCount - 1.0);
  float u = f - lo;
  vec3 p = mix(cadFrame(lo, 0.0), cadFrame(hi, 0.0), u);
  vec3 t = normalize(mix(cadFrame(lo, 1.0), cadFrame(hi, 1.0), u));
  vec3 n = mix(cadFrame(lo, 2.0), cadFrame(hi, 2.0), u);
  n = normalize(n - t * dot(n, t));
  vec3 v = cross(t, n);
  vec3 curvature = mix(cadFrame(lo, 3.0), cadFrame(hi, 3.0), u);
  float c = cos(cadTubeGpuParameters.x);
  float s = sin(cadTubeGpuParameters.x);
  vec2 transverse = mat2(c, s, -s, c) * a.yz;
  vec3 offset = n * transverse.x + v * transverse.y;
  float metric = 1.0 - dot(curvature, offset);
  vec2 normalPair = mat2(c, s, -s, c) * b.xy;
  vec3 normalValue = n * normalPair.x + v * normalPair.y + t * b.z * b.w / (metric * cadTubeGpuParameters.y);
  cadGpuPoint = (cadTubeGpuInverse * vec4(p + offset + a.w * t, 1.0)).xyz;
  cadGpuNormal = normalize(cadTubeGpuNormalMatrix * normalValue);
}
`;p(Df,"applyGpuStage");p(er,"patchMaterial");p(ir,"disableGpuTube");p(sr,"syncGpuTubeMaterials");p(Uf,"createGpuState");p(Ff,"installRaycastGuard");p(na,"applyGpuTube")});var va={};ja(va,{applyRecordTubeDeformation:()=>td,applyTubeDeformationToLineObject:()=>ur,compileDeformation:()=>Zt,compileTubePath:()=>xa,normalizeTubeDeformation:()=>Yf,poseTubeBake:()=>Fn,prepareTubeBake:()=>hr,projectTubePath:()=>Dn,restMappingKey:()=>Un,sameTubeDeformation:()=>Pe,sameTubeRestShape:()=>cr,sampleTubePath:()=>nn});function Bf(n,t){let e=0;for(let i=0;i<3;i++)e+=Math.max(n.min[i]-t[i],0,t[i]-n.max[i])**2;return e}function ut(n){throw new Error(`animation deformTube: ${n}`)}function Re(n,t){return(!Array.isArray(n)||n.length!==3||!n.every(Number.isFinite))&&ut(`${t} must be a finite vec3`),n.slice()}function je(n,t){let e=Gt(n);return e<Ie&&ut(`${t} must be nonzero`),St(n,1/e)}function Ci(n,t,e){(!n||typeof n!="object"||Array.isArray(n))&&ut(`${e} must be an object`);for(let i of Object.keys(n))t.includes(i)||ut(`unknown ${e} key ${JSON.stringify(i)}; expected ${t.join(", ")}`)}function Ri(n,t,e){let i=Math.cos(e),s=Math.sin(e);return tn(tn(St(n,i),St(xe(t,n),s)),St(t,ht(t,n)*(1-i)))}function Ln(n,t){let e=1-t;return[0,1,2].map(i=>e*e*e*n[0][i]+3*e*e*t*n[1][i]+3*e*t*t*n[2][i]+t*t*t*n[3][i])}function en(n,t){let e=1-t;return[0,1,2].map(i=>3*e*e*(n[1][i]-n[0][i])+6*e*t*(n[2][i]-n[1][i])+3*t*t*(n[3][i]-n[2][i]))}function ha(n,t){return[0,1,2].map(e=>6*(1-t)*(n[2][e]-2*n[1][e]+n[0][e])+6*t*(n[3][e]-2*n[2][e]+n[1][e]))}function Nn(n,t,e){let i=(t+e)/2,s=(e-t)/2,r=0;for(let o=0;o<5;o++){let a=i+s*zf[o],c=1-a,l=3*c*c,u=6*c*a,h=3*a*a,f=l*(n[1][0]-n[0][0])+u*(n[2][0]-n[1][0])+h*(n[3][0]-n[2][0]),d=l*(n[1][1]-n[0][1])+u*(n[2][1]-n[1][1])+h*(n[3][1]-n[2][1]),m=l*(n[1][2]-n[0][2])+u*(n[2][2]-n[1][2])+h*(n[3][2]-n[2][2]);r+=kf[o]*Math.hypot(f,d,m)}return s*r}function fa(n,t,e){let i=xe(t,e),s=Gt(i),r=ht(t,e);return s<Ie?(r<0&&ut("path tangent reverses"),n.slice()):Ri(n,St(i,1/s),Math.atan2(s,r))}function Vf(n){let t=[{t:0,s:0,tangent:n.tangent,normal:n.normal}],e=p((i,s,r=0)=>{let o=(i+s)/2,a=Nn(n.points,i,s),c=Nn(n.points,i,o),l=Nn(n.points,o,s),u=je(en(n.points,i),"Bezier tangent"),h=je(en(n.points,s),"Bezier tangent");if(r<20&&(s-i>1/128||Math.abs(a-c-l)>1e-9||ht(u,h)<.9999)){e(i,o,r+1),e(o,s,r+1);return}ht(u,h)<.99&&ut("Bezier has a cusp or unresolved tangent");let f=t.at(-1);t.push({t:s,s:f.s+c+l,tangent:h,normal:fa(f.normal,f.tangent,h)})},"append");e(0,1),n.table=t,n.length=t.at(-1).s}function da(n,t){let e=n.table,i=0,s=e.length-1;for(;s-i>1;){let c=i+s>>1;e[c].s<t?i=c:s=c}let r=e[i],o=e[s],a=r.t+(o.t-r.t)*(t-r.s)/(o.s-r.s);for(let c=0;c<3;c++){let l=r.s+Nn(n.points,r.t,a)-t;if(Math.abs(l)<1e-11)break;a=Math.max(r.t,Math.min(o.t,a-l/Gt(en(n.points,a))))}return{t:a,lower:r}}function pa(n,t){return n.kind==="line"?tn(n.start,St(n.tangent,t)):n.kind==="bezier"?Ln(n.points,da(n,t).t):tn(n.center,Ri(n.radial,n.axis,t/n.radius*n.sign))}function ar(n,t){if(n.kind==="bezier"){let{t:a,lower:c}=da(n,t),l=en(n.points,a),u=Gt(l),h=St(l,1/u),f=fa(c.normal,c.tangent,h),d=ha(n.points,a),m=St(Ft(d,St(h,ht(d,h))),1/(u*u));return{point:Ln(n.points,a),tangent:h,normal:f,binormal:xe(h,f),curvature:m}}let e=n.kind==="arc"?t/n.radius*n.sign:0,i=e?Ri(n.tangent,n.axis,e):n.tangent,s=e?Ri(n.normal,n.axis,e):n.normal,r=pa(n,t),o=n.kind==="arc"?St(Ft(n.center,r),1/(n.radius*n.radius)):[0,0,0];return{point:r,tangent:i,normal:s,binormal:xe(i,s),curvature:o}}function ma(n){return Ci(n,["segments","normal"],"path"),(!Array.isArray(n.segments)||!n.segments.length)&&ut("path needs at least one segment"),n.normal===void 0&&ut("path normal is required: give both the rest and the posed path an explicit transverse normal seed"),Re(n.normal,"normal")}function ga(n,t){return Ci(n,oa[n.kind]||oa.arc,`segment ${t}`),n.kind==="line"?{kind:"line",start:Re(n.start,"start"),end:Re(n.end,"end")}:n.kind==="arc"?{kind:"arc",center:Re(n.center,"center"),axis:Re(n.axis,"axis"),start:Re(n.start,"start"),sweepDeg:n.sweepDeg}:n.kind==="bezier"?((!Array.isArray(n.points)||n.points.length!==4)&&ut("Bezier points must contain four vec3 control points"),{kind:"bezier",points:n.points.map(e=>Re(e,"Bezier point"))}):ut(`unknown segment kind ${JSON.stringify(n.kind)}; expected line, arc, bezier`)}function Gf(n,t){let e=ga(n,t);if(e.kind==="line"){let{start:s,end:r}=e,o=Ft(r,s);return{kind:"line",start:s,end:r,tangent:je(o,"line"),length:Gt(o),radius:1/0}}if(e.kind==="arc"){let{center:s,start:r}=e,o=je(e.axis,"axis"),a=Ft(r,s),c=Gt(a),l=e.sweepDeg*Math.PI/180;(!Number.isFinite(l)||Math.abs(l)<Ie||Math.abs(l)>2*Math.PI+Ie)&&ut("arc sweepDeg must be nonzero and at most 360 degrees"),(c<Ie||Math.abs(ht(a,o))>Ie*Math.max(1,c))&&ut("arc start must be in its normal plane with nonzero radius");let u=Math.sign(l),h=St(xe(o,a),u/c),f={kind:"arc",center:s,start:r,axis:o,radial:a,radius:c,sign:u,tangent:h,length:c*Math.abs(l)};return f.end=pa(f,f.length),f}let i=e.points;return{kind:"bezier",points:i,start:i[0],end:i[3],tangent:je(en(i,0),"Bezier tangent"),radius:1/0}}function Hf(n){return Math.min(...n.table.map(t=>{let e=en(n.points,t.t),i=ha(n.points,t.t),s=Gt(e);return Math.pow(s,3)/Gt(xe(e,i))}))}function Wf(n){if(n.kind==="arc")return{min:n.center.map(e=>e-n.radius),max:n.center.map(e=>e+n.radius)};let t=n.kind==="bezier"?n.points:[n.start,n.end];return{min:[0,1,2].map(e=>Math.min(...t.map(i=>i[e]))),max:[0,1,2].map(e=>Math.max(...t.map(i=>i[e])))}}function xa(n){let t=ma(n),e=0,i=null,s=n.segments.map((o,a)=>{let c=Gf(o,a);if(i){Gt(Ft(i.end,c.start))>1e-5&&ut(`path discontinuity before segment ${a}`);let l=ar(i,i.length);ht(l.tangent,c.tangent)<1-1e-7&&ut(`path is not tangent-continuous before segment ${a}`),c.normal=l.normal}else c.normal=je(Ft(t,St(c.tangent,ht(t,c.tangent))),"path normal transverse to first tangent");return c.kind==="bezier"&&Vf(c),c.offset=e,c.bounds=Wf(c),e+=c.length,i=c,c}),r={segments:s,length:e};return Object.defineProperty(r,"minRadius",{get(){for(let o of s)o.kind==="bezier"&&o.radius===1/0&&(o.radius=Hf(o));return Math.min(...s.map(o=>o.radius))}}),r}function nn(n,t){Number.isFinite(t)||ut("path distance must be finite");let e=t<=0?n.segments[0]:n.segments.find(o=>t<=o.offset+o.length)||n.segments.at(-1),i=t-e.offset,s=Math.max(0,Math.min(e.length,i)),r=ar(e,s);return i!==s&&(r.point=tn(r.point,St(r.tangent,i-s))),r}function Xf(n){if(!n.tablePoints){let t=new Float64Array(n.table.length*3);n.table.forEach((e,i)=>{let s=Ln(n.points,e.t);t[i*3]=s[0],t[i*3+1]=s[1],t[i*3+2]=s[2]}),n.tablePoints=t}return n.tablePoints}function qf(n,t){let e=Xf(n),i=0,s=1/0;for(let l=0;l<n.table.length;l++){let u=(t[0]-e[l*3])**2+(t[1]-e[l*3+1])**2+(t[2]-e[l*3+2])**2;u<s&&(s=u,i=l)}let r=n.table[Math.max(0,i-1)].t,o=n.table[Math.min(n.table.length-1,i+1)].t;for(let l=0;l<35;l++){let u=r+(o-r)/3,h=o-(o-r)/3;ra(t,Ln(n.points,u))<ra(t,Ln(n.points,h))?o=h:r=u}let a=(r+o)/2,c=n.table.findLast(l=>l.t<=a)||n.table[0];return c.s+Nn(n.points,c.t,a)}function $f(n,t){let e=Ft(t,n.center),i=Math.atan2(ht(xe(n.radial,e),n.axis),ht(n.radial,e))*n.sign;i<0&&(i+=2*Math.PI);let s=i*n.radius;return s>n.length?Gt(Ft(t,n.start))<Gt(Ft(t,n.end))?0:n.length:s}function Dn(n,t){let e=null,i=n.segments.map(s=>({segment:s,bound:Bf(s.bounds,t)})).sort((s,r)=>s.bound-r.bound);for(let{segment:s,bound:r}of i){if(e&&r>e.distanceSq+1e-12)break;let o;s.kind==="line"?o=ht(Ft(t,s.start),s.tangent):s.kind==="bezier"?o=qf(s,t):o=$f(s,t),o=Math.max(0,Math.min(s.length,o));let a=ar(s,o),c=Ft(t,a.point),l=ht(c,c);(!e||l<e.distanceSq)&&(e={distance:s.offset+o,distanceSq:l,transverse:[ht(c,a.normal),ht(c,a.binormal)],axial:ht(c,a.tangent)})}return e}function aa(n){let t=JSON.stringify(n),e=Ke.get(t);return e?Ke.delete(t):e=xa(n),Ke.set(t,e),Ke.size>Of&&Ke.delete(Ke.keys().next().value),e}function ca(n){return{normal:ma(n),segments:n.segments.map((t,e)=>ga(t,e))}}function Qe(n,t){if(n===t)return!0;if(Array.isArray(n))return!Array.isArray(t)||n.length!==t.length?!1:n.every((e,i)=>Qe(e,t[i]));if(n&&typeof n=="object"){if(!t||typeof t!="object"||Array.isArray(t))return!1;let e=Object.keys(n);return e.length===Object.keys(t).length&&e.every(i=>Qe(n[i],t[i]))}return!1}function Pe(n,t){return n===t?!0:!n||!t?!1:n.twistDeg===t.twistDeg&&n.maxSegmentLength===t.maxSegmentLength&&Qe(n.braid,t.braid)&&Qe(n.restSpec,t.restSpec)&&Qe(n.pathSpec,t.pathSpec)}function cr(n,t){return n.maxSegmentLength===t.maxSegmentLength&&Qe(n.restSpec,t.restSpec)}function Zt(n){return{...n,rest:aa(n.restSpec),path:aa(n.pathSpec)}}function Yf(n){Ci(n,["rest","path","twistDeg","maxSegmentLength","braid"],"deformation");let t=n.twistDeg??0;Number.isFinite(t)||ut("twistDeg must be finite");let e=n.maxSegmentLength??1;(!Number.isFinite(e)||e<.05)&&ut("maxSegmentLength must be at least 0.05 mm");let i=null;if(n.braid){Ci(n.braid,["pitch","depth","strands"],"braid");let{pitch:s,depth:r,strands:o}=n.braid;Number.isFinite(s)&&s>0&&Number.isFinite(r)&&r>=0&&Number.isInteger(o)&&o>=2&&o<=64&&o%2===0||ut("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64"),i={pitch:s,depth:r,strands:o}}return{restSpec:ca(n.rest),pathSpec:ca(n.path),twistDeg:t,maxSegmentLength:e,braid:i}}function la(n,t,e){let i=[];for(let s=0;s<n.length;s++){let r=n[s],o=n[(s+1)%n.length],a=e?r[0]>=t:r[0]<=t,c=e?o[0]>=t:o[0]<=t;if(a&&i.push(r),a!==c){let l=(t-r[0])/(o[0]-r[0]);i.push(r.map((u,h)=>u+l*(o[h]-u)))}}return i.filter((s,r)=>!r||Math.abs(s[1]-i[r-1][1])+Math.abs(s[2]-i[r-1][2])+Math.abs(s[3]-i[r-1][3])>1e-10)}function Zf(n,t,e,i,s){if(s>=e.length)return{geometry:t,sourceTriangles:null};let r=t.attributes.position,o=new n.Vector3,a=new Float64Array(r.count),c=new Map;for(let x=0;x<r.count;x++){let v=[r.getX(x),r.getY(x),r.getZ(x)].join(","),y=c.get(v);y===void 0&&(o.fromBufferAttribute(r,x).applyMatrix4(i),y=Dn(e,o.toArray()).distance,c.set(v,y)),a[x]=y}c.clear();let l=t.index?.count??r.count;if(l%3)return{geometry:t.clone(),sourceTriangles:null};let u=Object.entries(t.attributes),h=Object.fromEntries(u.map(([x])=>[x,[]])),f=[],d=[],m=new Map,g=p(x=>t.index?t.index.getX(x):x,"index");for(let x=0;x<l;x+=3){let v=[g(x),g(x+1),g(x+2)],y=v.map(M=>a[M]),b=y.map((M,T)=>[M,...[0,1,2].map(I=>T===I?1:0)]),S=Math.floor(Math.min(...y)/s),A=Math.floor(Math.max(...y)/s);for(let M=S;M<=A;M++){let T=la(la(b,M*s,!0),(M+1)*s,!1);for(let I=1;I<T.length-1;I++){let E=[T[0],T[I],T[I+1]],N=Ft(E[1].slice(1),E[0].slice(1)),L=Ft(E[2].slice(1),E[0].slice(1));if(!(Gt(xe(N,L))<1e-12)){f.push(x/3),f.length>sa&&ut(`refined tube exceeds ${sa} triangles; increase maxSegmentLength`);for(let R of E){let C=v.map((w,U)=>[w,Math.round(R[U+1]*1e10)]).filter(([,w])=>w).sort((w,U)=>w[0]-U[0]).map(w=>w.join(":")).join(","),P=m.get(C);if(P===void 0){P=m.size,m.set(C,P);for(let[w,U]of u)for(let F=0;F<U.itemSize;F++)h[w].push(v.reduce((D,O,k)=>D+R[k+1]*U.getComponent(O,F),0))}d.push(P)}}}}}let _=t.clone();for(let[x,v]of u)_.setAttribute(x,new n.Float32BufferAttribute(h[x],v.itemSize));return _.setIndex(d),_.clearGroups(),{geometry:_,sourceTriangles:new Uint32Array(f)}}function _a(n,t,e,i,s,r=!1){let o=[],a=r?new Float32Array(t.count):new Uint32Array(t.count),c=new Map,l=new n.Vector3,u=new n.Matrix3().getNormalMatrix(s),h=new n.Vector3;for(let d=0;d<t.count;d++){let m=[t.getX(d),t.getY(d),t.getZ(d),...e?[e.getX(d),e.getY(d),e.getZ(d)]:[]].join(","),g=c.get(m);if(g!==void 0){a[d]=g;continue}let _=o.length/8;c.set(m,_),a[d]=_,l.fromBufferAttribute(t,d).applyMatrix4(s);let x=Dn(i,[l.x,l.y,l.z]),v=nn(i,x.distance),y=tn(St(v.normal,x.transverse[0]),St(v.binormal,x.transverse[1])),b=1-ht(v.curvature,y);b<=Ie&&ut("rest mesh crosses the centerline curvature radius");let S=[0,0,0];if(e){h.fromBufferAttribute(e,d).applyNormalMatrix(u);let A=[h.x,h.y,h.z];S=[ht(A,v.normal),ht(A,v.binormal),ht(A,v.tangent)]}o.push(x.distance/i.length,...x.transverse,x.axial,...S,b)}let f=r?new Float32Array(Math.ceil(o.length/4096)*4096):new Float64Array(o.length);return f.set(o),{values:f,indices:a,gpu:r}}function lr(n,t,e,i,s,r){let{path:o,rest:a}=s,c=new n.Vector3,l=new n.Vector3,u=new n.Matrix3().getNormalMatrix(r),h=s.twistDeg*Math.PI/180,f=Math.cos(h),d=Math.sin(h),m=o.length/a.length,g=new Map,_=i.values,x=new Map;for(let v=0;v<t.count;v++){let y=i.indices[v],b=x.get(y);if(b!==void 0){t.setXYZ(v,t.getX(b),t.getY(b),t.getZ(b)),e&&e.setXYZ(v,e.getX(b),e.getY(b),e.getZ(b));continue}x.set(y,v);let S=y*8,A=_[S],M=g.get(A);M||(M=nn(o,A*o.length),g.set(A,M));let T=f*_[S+1]-d*_[S+2],I=d*_[S+1]+f*_[S+2],E=M.normal[0]*T+M.binormal[0]*I,N=M.normal[1]*T+M.binormal[1]*I,L=M.normal[2]*T+M.binormal[2]*I,R=M.curvature[0]*E+M.curvature[1]*N+M.curvature[2]*L;if(1-R<=rr){let P=(1-rr)/R;E*=P,N*=P,L*=P,R=1-rr}let C=1-R;if(c.set(M.point[0]+E+_[S+3]*M.tangent[0],M.point[1]+N+_[S+3]*M.tangent[1],M.point[2]+L+_[S+3]*M.tangent[2]).applyMatrix4(r),t.setXYZ(v,c.x,c.y,c.z),e){let P=f*_[S+4]-d*_[S+5],w=d*_[S+4]+f*_[S+5],U=_[S+6]*_[S+7]/(C*m);l.set(P*M.normal[0]+w*M.binormal[0]+U*M.tangent[0],P*M.normal[1]+w*M.binormal[1]+U*M.tangent[1],P*M.normal[2]+w*M.binormal[2]+U*M.tangent[2]).applyNormalMatrix(u),e.setXYZ(v,l.x,l.y,l.z)}}t.needsUpdate=!0,e&&(e.needsUpdate=!0)}function Jf(n,t,e,i,s,r){let o=e.clone(),a=e.attributes.instanceStart,c=e.attributes.instanceEnd,l=e.attributes.position;if(!a&&!l)return o;let u=a?null:e.index,h=a?a.count:u?u.count/2:t.isLineSegments?l.count/2:l.count-1,f=p((y,b)=>u?u.getX(y*2+b):t.isLineSegments?y*2+b:y+b,"vertexOf"),d=a?[]:Object.entries(e.attributes).filter(([y])=>y!=="position"),m=Object.fromEntries(d.map(([y])=>[y,[]])),g=new n.Vector3,_=new n.Vector3,x=new n.Vector3,v=[];for(let y=0;y<h;y++){let b=a?y:f(y,0),S=c?y:f(y,1);g.fromBufferAttribute(a||l,b),_.fromBufferAttribute(c||l,S);let A=Dn(i,x.copy(g).applyMatrix4(s).toArray()).distance,M=Dn(i,x.copy(_).applyMatrix4(s).toArray()).distance,T=Math.max(1,Math.ceil(Math.abs(M-A)/r));for(let I=0;I<T;I++)for(let E of[I/T,(I+1)/T]){v.push(g.x+(_.x-g.x)*E,g.y+(_.y-g.y)*E,g.z+(_.z-g.z)*E);for(let[N,L]of d){let R=E<1?b:S;for(let C=0;C<L.itemSize;C++)m[N].push(L.array[R*L.itemSize+C])}}}if(a)o.setPositions(v);else{o.setAttribute("position",new n.Float32BufferAttribute(v,3));for(let[y,b]of d)o.setAttribute(y,new n.BufferAttribute(new b.array.constructor(m[y]),b.itemSize,b.normalized));o.setIndex(null)}return o}function ur(n,t,e,i=new n.Matrix4){if(!t)return;for(let c of t.children||[])ur(n,c,e,i);if(!t.geometry)return;let s=t.tubeLineDeformationState;if(!e&&!s?.active||e&&s?.active&&Pe(s.lastSpec,e))return;let r=e?Zt(e):null,o=e?Un(e):s?.restKey;if(!s||e&&o!==s.restKey){let c=s?.original||t.geometry,l=Jf(n,t,c,r.rest,i,r.maxSegmentLength),u=l.clone();s?.geometry.dispose(),u.userData={...u.userData,cadSceneCachedGeometry:!1};let h=l.attributes.instanceStart?["instanceStart","instanceEnd"]:["position"];s=t.tubeLineDeformationState={original:c,source:l,geometry:u,names:h,mappings:{},restKey:null,active:!1},t.geometry=u}if(!e){for(let c of s.names){let l=s.geometry.attributes[c],u=s.source.attributes[c];for(let h=0;h<u.count;h++)l.setXYZ(h,u.getX(h),u.getY(h),u.getZ(h));l.needsUpdate=!0}s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere(),s.active=!1;return}let a=i.clone().invert();for(let c of s.names)o!==s.restKey&&(s.mappings[c]=_a(n,s.source.attributes[c],null,r.rest,i)),lr(n,s.geometry.attributes[c],null,s.mappings[c],r,a);s.restKey=o,s.active=!0,s.lastSpec=e,s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere()}function Kf(n,t){return`${Un(n)}|${t.elements.map(e=>Number(e).toPrecision(9)).join(",")}`}function ya(n,t,e,i){let s=ua.get(t);s||(s=new Map,ua.set(t,s));let r=Kf(e,i),o=s.get(r);if(!o){let a=Zf(n,t,e.rest,i,e.maxSegmentLength);o={restSource:a.geometry,sourceTriangles:a.sourceTriangles,mappings:new Map},s.set(r,o)}return o}function or(n,t,e,i,s){let r=s?"gpu":"exact",o=t.mappings.get(r);return o||(o=_a(n,t.restSource.attributes.position,t.restSource.attributes.normal,e.rest,i,s),t.mappings.set(r,o)),o}function hr(n,t,e,i){let s=ya(n,t,e,i);return{geometry:s.restSource,sourceTriangles:s.sourceTriangles,mapping:or(n,s,e,i,!1),vertexCount:s.restSource.attributes.position.count}}function Fn(n,t,e,i,s,r=null){lr(n,s,r,t.mapping,e,i)}function jf(n,t,e,i,s){let r=e?.original||t.mesh.geometry,o=e?.originalFaceIds||t.mesh.userData?.faceIds,a=ya(n,r,i,s),c=a.restSource,l=new n.BufferGeometry;l.setIndex(c.index);for(let[h,f]of Object.entries(c.attributes)){let d=!t.gpuTubeDeformationAllowed&&(h==="position"||h==="normal");l.setAttribute(h,d?f.clone():f)}l.userData={...l.userData,cadSceneCachedGeometry:!1,__bvhSkipped:!0},l.boundsTree=null,e?.geometry.dispose();let u={original:r,originalFaceIds:o,source:c,prepared:a,geometry:l,active:!1,restKey:Un(i),mapping:null,partBounds:e?.partBounds||t.partBounds};return t.mesh.geometry=l,o&&a.sourceTriangles&&(t.mesh.userData.faceIds=new Uint32Array(a.sourceTriangles.map(h=>o[h]))),t.geometry=l,t.silhouette&&(t.silhouette.geometry=l),t.ghostMesh&&(t.ghostMesh.geometry=l),u}function Qf(n,t){t.geometry.attributes.position.copy(t.source.attributes.position),t.geometry.attributes.position.needsUpdate=!0,t.source.attributes.normal&&(t.geometry.attributes.normal.copy(t.source.attributes.normal),t.geometry.attributes.normal.needsUpdate=!0),t.geometry.computeBoundingBox(),t.geometry.computeBoundingSphere(),n.partBounds=t.partBounds,t.active=!1}function td(n,t,e){if(!t?.mesh?.geometry)return;t.effectDeformation=e||null,ta(n,t.material||t.mesh.material,e?.braid||null),e&&t.edgeInstance&&t.detachEdgeInstance?.();let i=new n.Matrix4;t.baseTransform&&i.fromArray(t.baseTransform).transpose(),(!e||t.edges?.visible!==!1)&&ur(n,t.edges,e,i);let s=t.tubeDeformationState;if(e&&s?.active&&Pe(s.lastSpec,e)){sr(t);return}if(!e&&!s?.active)return;let r=e?Zt(e):null;if(e||ir(t),(!s||e&&Un(e)!==s.restKey)&&(s=t.tubeDeformationState=jf(n,t,s,r,i)),!e){Qf(t,s);return}let o=i.clone().invert(),a=t.gpuTubeDeformationAllowed&&r.path.length<=nr;if(!s.mapping&&(s.mapping=or(n,s.prepared,r,i,a),!s.mapping.gpu)){let u=new Float32Array(s.geometry.attributes.position.count*3);for(let h=0;h<u.length/3;h++){let f=s.mapping.indices[h]*8,d=s.mapping.values;u.set([d[f]*r.rest.length,d[f+1],d[f+2]],h*3)}s.geometry.setAttribute(Pn,new n.BufferAttribute(u,3))}let c=p(()=>{for(let u of["position","normal"])s.geometry.attributes[u]===s.source.attributes[u]&&s.geometry.setAttribute(u,s.source.attributes[u].clone());s.exactMapping??=s.mapping.gpu?or(n,s.prepared,r,i,!1):s.mapping,lr(n,s.geometry.attributes.position,s.geometry.attributes.normal,s.exactMapping,r,o),s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere()},"materialize");if(na(n,t,s,r,o,nn,c)){s.active=!0,s.lastSpec=e;return}ir(t),c();let l=s.geometry.boundingBox.clone().applyMatrix4(i);t.partBounds={min:l.min.toArray(),max:l.max.toArray()},s.active=!0,s.lastSpec=e}var Ie,rr,sa,Of,tn,Ft,St,ht,xe,Gt,ra,zf,kf,oa,Ke,Un,ua,Ii=zn(()=>{ea();ia();Ei();Ie=1e-7,rr=.05,sa=7e5,Of=128,tn=p((n,t)=>n.map((e,i)=>e+t[i]),"add"),Ft=p((n,t)=>n.map((e,i)=>e-t[i]),"sub"),St=p((n,t)=>n.map(e=>e*t),"mul"),ht=p((n,t)=>n.reduce((e,i,s)=>e+i*t[s],0),"dot"),xe=p((n,t)=>[n[1]*t[2]-n[2]*t[1],n[2]*t[0]-n[0]*t[2],n[0]*t[1]-n[1]*t[0]],"cross"),Gt=p(n=>Math.hypot(...n),"length"),ra=p((n,t)=>(n[0]-t[0])**2+(n[1]-t[1])**2+(n[2]-t[2])**2,"distanceSq");p(Bf,"boundsDistanceSq");p(ut,"fail");p(Re,"vector");p(je,"unit");p(Ci,"keys");p(Ri,"rotate");p(Ln,"bezierAt");p(en,"bezierDerivative");p(ha,"bezierSecond");zf=[0,.5384693101056831,-.5384693101056831,.906179845938664,-.906179845938664],kf=[.5688888888888889,.4786286704993665,.4786286704993665,.2369268850561891,.2369268850561891];p(Nn,"bezierLength");p(fa,"transport");p(Vf,"buildBezierTable");p(da,"bezierParameter");p(pa,"segmentPoint");p(ar,"segmentFrame");oa={line:["kind","start","end"],arc:["kind","center","axis","start","sweepDeg"],bezier:["kind","points"]};p(ma,"pathSpecNormal");p(ga,"canonicalSegment");p(Gf,"compileSegment");p(Hf,"sampledBezierRadius");p(Wf,"segmentBounds");p(xa,"compileTubePath");p(nn,"sampleTubePath");p(Xf,"tablePoints");p(qf,"closestBezierDistance");p($f,"closestArcDistance");p(Dn,"projectTubePath");Ke=new Map;p(aa,"cachedCompile");p(ca,"canonicalPathSpec");p(Qe,"sameNumbers");p(Pe,"sameTubeDeformation");p(cr,"sameTubeRestShape");p(Zt,"compileDeformation");p(Yf,"normalizeTubeDeformation");Un=p(n=>JSON.stringify([n.restSpec,n.maxSegmentLength]),"restMappingKey");p(la,"clipPolygon");p(Zf,"refineRestMesh");p(_a,"mappingFor");p(lr,"updateAttribute");p(Jf,"refineLineGeometry");p(ur,"applyTubeDeformationToLineObject");ua=new WeakMap;p(Kf,"restPreparationKey");p(ya,"prepareRestSurface");p(or,"preparedMapping");p(hr,"prepareTubeBake");p(Fn,"poseTubeBake");p(jf,"createDeformationState");p(Qf,"restoreRestSurface");p(td,"applyRecordTubeDeformation")});import on from"node:fs";import an from"node:path";function Sr(n){let t=new DataView(n,0,12);if(t.getUint32(0,!0)!==1179800915)throw new Error("not a SURF container");let e=t.getUint32(4,!0);if(e!==2)throw new Error(`unsupported SURF version ${e}`);let i=t.getUint32(8,!0),s=new Uint8Array(n,12,i),r=JSON.parse(new TextDecoder().decode(s)),o=12+i,a=new Float32Array(n.slice(o,o+(n.byteLength-o>>2<<2)));return{index:r,floats:a}}p(Sr,"parseSurf");function se(n,t){let[e,i]=t;return n.subarray(e,e+i)}p(se,"floatSpan");var zr=1;var kr=3;var $i=0,Yi=1,Zi=2,Ji=3,Ki=4,ji=5,Qi=6,ts=7,Vr=0,Gr=1,Hr=2;var _s=1,ys=2,vs=3,Ms=4,bs=5,Ss=6,As=7;var Ts=300,Wr=301,ws=302;var Xr=306,es=1e3,pn=1001,ns=1002;var qr=1006;var $r=1008;var Yr=1009;var Zr=1015;var Jr=1023;var xn=2300,jn=2301,Jn=2302,is=2303,ss=2400,rs=2401,os=2402;var Es="",kt="srgb",as="srgb-linear",cs="linear",Kn="srgb";var ls=35044;var mn=2e3,us=2001;function Qa(n){for(let t=n.length-1;t>=0;--t)if(n[t]>=65535)return!0;return!1}p(Qa,"arrayNeedsUint32");function tc(n){return ArrayBuffer.isView(n)&&!(n instanceof DataView)}p(tc,"isTypedArray");function hs(n){return document.createElementNS("http://www.w3.org/1999/xhtml",n)}p(hs,"createElementNS");var Ar={},Qn=null;function Kr(n){let t=n[0];if(typeof t=="string"&&t.startsWith("TSL:")){let e=n[1];e&&e.isStackTrace?n[0]+=" "+e.getLocation():n[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return n}p(Kr,"enhanceLogMessage");function pt(...n){n=Kr(n);let t="THREE."+n.shift();if(Qn)Qn("warn",t,...n);else{let e=n[0];e&&e.isStackTrace?console.warn(e.getError(t)):console.warn(t,...n)}}p(pt,"warn");function rt(...n){n=Kr(n);let t="THREE."+n.shift();if(Qn)Qn("error",t,...n);else{let e=n[0];e&&e.isStackTrace?console.error(e.getError(t)):console.error(t,...n)}}p(rt,"error");function He(...n){let t=n.join(" ");t in Ar||(Ar[t]=!0,pt(...n))}p(He,"warnOnce");var ec={[$i]:Yi,[Zi]:Qi,[Ki]:ts,[Ji]:ji,[Yi]:$i,[Qi]:Zi,[ts]:Ki,[ji]:Ji},Me=class{static{p(this,"EventDispatcher")}addEventListener(t,e){this._listeners===void 0&&(this._listeners={});let i=this._listeners;i[t]===void 0&&(i[t]=[]),i[t].indexOf(e)===-1&&i[t].push(e)}hasEventListener(t,e){let i=this._listeners;return i===void 0?!1:i[t]!==void 0&&i[t].indexOf(e)!==-1}removeEventListener(t,e){let i=this._listeners;if(i===void 0)return;let s=i[t];if(s!==void 0){let r=s.indexOf(e);r!==-1&&s.splice(r,1)}}dispatchEvent(t){let e=this._listeners;if(e===void 0)return;let i=e[t.type];if(i!==void 0){t.target=this;let s=i.slice(0);for(let r=0,o=s.length;r<o;r++)s[r].call(this,t);t.target=null}}},vt=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];var kd=Math.PI/180,nc=180/Math.PI;function gi(){let n=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,i=Math.random()*4294967295|0;return(vt[n&255]+vt[n>>8&255]+vt[n>>16&255]+vt[n>>24&255]+"-"+vt[t&255]+vt[t>>8&255]+"-"+vt[t>>16&15|64]+vt[t>>24&255]+"-"+vt[e&63|128]+vt[e>>8&255]+"-"+vt[e>>16&255]+vt[e>>24&255]+vt[i&255]+vt[i>>8&255]+vt[i>>16&255]+vt[i>>24&255]).toLowerCase()}p(gi,"generateUUID");function j(n,t,e){return Math.max(t,Math.min(e,n))}p(j,"clamp");function ic(n,t){return(n%t+t)%t}p(ic,"euclideanModulo");function Oi(n,t,e){return(1-e)*n+e*t}p(Oi,"lerp");function ln(n,t){switch(t.constructor){case Float32Array:return n;case Uint32Array:return n/4294967295;case Uint16Array:return n/65535;case Uint8Array:return n/255;case Int32Array:return Math.max(n/2147483647,-1);case Int16Array:return Math.max(n/32767,-1);case Int8Array:return Math.max(n/127,-1);default:throw new Error("THREE.MathUtils: Invalid component type.")}}p(ln,"denormalize");function Tt(n,t){switch(t.constructor){case Float32Array:return n;case Uint32Array:return Math.round(n*4294967295);case Uint16Array:return Math.round(n*65535);case Uint8Array:return Math.round(n*255);case Int32Array:return Math.round(n*2147483647);case Int16Array:return Math.round(n*32767);case Int8Array:return Math.round(n*127);default:throw new Error("THREE.MathUtils: Invalid component type.")}}p(Tt,"normalize");var mt=class n{static{p(this,"Vector2")}static{n.prototype.isVector2=!0}constructor(t=0,e=0){this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("THREE.Vector2: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){let e=this.x,i=this.y,s=t.elements;return this.x=s[0]*e+s[3]*i+s[6],this.y=s[1]*e+s[4]*i+s[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=j(this.x,t.x,e.x),this.y=j(this.y,t.y,e.y),this}clampScalar(t,e){return this.x=j(this.x,t,e),this.y=j(this.y,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(j(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let i=this.dot(t)/e;return Math.acos(j(i,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,i=this.y-t.y;return e*e+i*i}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){let i=Math.cos(e),s=Math.sin(e),r=this.x-t.x,o=this.y-t.y;return this.x=r*i-o*s+t.x,this.y=r*s+o*i+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},qt=class{static{p(this,"Quaternion")}constructor(t=0,e=0,i=0,s=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=i,this._w=s}static slerpFlat(t,e,i,s,r,o,a){let c=i[s+0],l=i[s+1],u=i[s+2],h=i[s+3],f=r[o+0],d=r[o+1],m=r[o+2],g=r[o+3];if(h!==g||c!==f||l!==d||u!==m){let _=c*f+l*d+u*m+h*g;_<0&&(f=-f,d=-d,m=-m,g=-g,_=-_);let x=1-a;if(_<.9995){let v=Math.acos(_),y=Math.sin(v);x=Math.sin(x*v)/y,a=Math.sin(a*v)/y,c=c*x+f*a,l=l*x+d*a,u=u*x+m*a,h=h*x+g*a}else{c=c*x+f*a,l=l*x+d*a,u=u*x+m*a,h=h*x+g*a;let v=1/Math.sqrt(c*c+l*l+u*u+h*h);c*=v,l*=v,u*=v,h*=v}}t[e]=c,t[e+1]=l,t[e+2]=u,t[e+3]=h}static multiplyQuaternionsFlat(t,e,i,s,r,o){let a=i[s],c=i[s+1],l=i[s+2],u=i[s+3],h=r[o],f=r[o+1],d=r[o+2],m=r[o+3];return t[e]=a*m+u*h+c*d-l*f,t[e+1]=c*m+u*f+l*h-a*d,t[e+2]=l*m+u*d+a*f-c*h,t[e+3]=u*m-a*h-c*f-l*d,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,i,s){return this._x=t,this._y=e,this._z=i,this._w=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){let i=t._x,s=t._y,r=t._z,o=t._order,a=Math.cos,c=Math.sin,l=a(i/2),u=a(s/2),h=a(r/2),f=c(i/2),d=c(s/2),m=c(r/2);switch(o){case"XYZ":this._x=f*u*h+l*d*m,this._y=l*d*h-f*u*m,this._z=l*u*m+f*d*h,this._w=l*u*h-f*d*m;break;case"YXZ":this._x=f*u*h+l*d*m,this._y=l*d*h-f*u*m,this._z=l*u*m-f*d*h,this._w=l*u*h+f*d*m;break;case"ZXY":this._x=f*u*h-l*d*m,this._y=l*d*h+f*u*m,this._z=l*u*m+f*d*h,this._w=l*u*h-f*d*m;break;case"ZYX":this._x=f*u*h-l*d*m,this._y=l*d*h+f*u*m,this._z=l*u*m-f*d*h,this._w=l*u*h+f*d*m;break;case"YZX":this._x=f*u*h+l*d*m,this._y=l*d*h+f*u*m,this._z=l*u*m-f*d*h,this._w=l*u*h-f*d*m;break;case"XZY":this._x=f*u*h-l*d*m,this._y=l*d*h-f*u*m,this._z=l*u*m+f*d*h,this._w=l*u*h+f*d*m;break;default:pt("Quaternion: .setFromEuler() encountered an unknown order: "+o)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){let i=e/2,s=Math.sin(i);return this._x=t.x*s,this._y=t.y*s,this._z=t.z*s,this._w=Math.cos(i),this._onChangeCallback(),this}setFromRotationMatrix(t){let e=t.elements,i=e[0],s=e[4],r=e[8],o=e[1],a=e[5],c=e[9],l=e[2],u=e[6],h=e[10],f=i+a+h;if(f>0){let d=.5/Math.sqrt(f+1);this._w=.25/d,this._x=(u-c)*d,this._y=(r-l)*d,this._z=(o-s)*d}else if(i>a&&i>h){let d=2*Math.sqrt(1+i-a-h);this._w=(u-c)/d,this._x=.25*d,this._y=(s+o)/d,this._z=(r+l)/d}else if(a>h){let d=2*Math.sqrt(1+a-i-h);this._w=(r-l)/d,this._x=(s+o)/d,this._y=.25*d,this._z=(c+u)/d}else{let d=2*Math.sqrt(1+h-i-a);this._w=(o-s)/d,this._x=(r+l)/d,this._y=(c+u)/d,this._z=.25*d}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let i=t.dot(e)+1;return i<1e-8?(i=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=i):(this._x=0,this._y=-t.z,this._z=t.y,this._w=i)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=i),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(j(this.dot(t),-1,1)))}rotateTowards(t,e){let i=this.angleTo(t);if(i===0)return this;let s=Math.min(1,e/i);return this.slerp(t,s),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){let i=t._x,s=t._y,r=t._z,o=t._w,a=e._x,c=e._y,l=e._z,u=e._w;return this._x=i*u+o*a+s*l-r*c,this._y=s*u+o*c+r*a-i*l,this._z=r*u+o*l+i*c-s*a,this._w=o*u-i*a-s*c-r*l,this._onChangeCallback(),this}slerp(t,e){let i=t._x,s=t._y,r=t._z,o=t._w,a=this.dot(t);a<0&&(i=-i,s=-s,r=-r,o=-o,a=-a);let c=1-e;if(a<.9995){let l=Math.acos(a),u=Math.sin(l);c=Math.sin(c*l)/u,e=Math.sin(e*l)/u,this._x=this._x*c+i*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this._onChangeCallback()}else this._x=this._x*c+i*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this.normalize();return this}slerpQuaternions(t,e,i){return this.copy(t).slerp(e,i)}random(){let t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),i=Math.random(),s=Math.sqrt(1-i),r=Math.sqrt(i);return this.set(s*Math.sin(t),s*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},V=class n{static{p(this,"Vector3")}static{n.prototype.isVector3=!0}constructor(t=0,e=0,i=0){this.x=t,this.y=e,this.z=i}set(t,e,i){return i===void 0&&(i=this.z),this.x=t,this.y=e,this.z=i,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("THREE.Vector3: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(Tr.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(Tr.setFromAxisAngle(t,e))}applyMatrix3(t){let e=this.x,i=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[3]*i+r[6]*s,this.y=r[1]*e+r[4]*i+r[7]*s,this.z=r[2]*e+r[5]*i+r[8]*s,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){let e=this.x,i=this.y,s=this.z,r=t.elements,o=1/(r[3]*e+r[7]*i+r[11]*s+r[15]);return this.x=(r[0]*e+r[4]*i+r[8]*s+r[12])*o,this.y=(r[1]*e+r[5]*i+r[9]*s+r[13])*o,this.z=(r[2]*e+r[6]*i+r[10]*s+r[14])*o,this}applyQuaternion(t){let e=this.x,i=this.y,s=this.z,r=t.x,o=t.y,a=t.z,c=t.w,l=2*(o*s-a*i),u=2*(a*e-r*s),h=2*(r*i-o*e);return this.x=e+c*l+o*h-a*u,this.y=i+c*u+a*l-r*h,this.z=s+c*h+r*u-o*l,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){let e=this.x,i=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[4]*i+r[8]*s,this.y=r[1]*e+r[5]*i+r[9]*s,this.z=r[2]*e+r[6]*i+r[10]*s,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=j(this.x,t.x,e.x),this.y=j(this.y,t.y,e.y),this.z=j(this.z,t.z,e.z),this}clampScalar(t,e){return this.x=j(this.x,t,e),this.y=j(this.y,t,e),this.z=j(this.z,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(j(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this.z=t.z+(e.z-t.z)*i,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){let i=t.x,s=t.y,r=t.z,o=e.x,a=e.y,c=e.z;return this.x=s*c-r*a,this.y=r*o-i*c,this.z=i*a-s*o,this}projectOnVector(t){let e=t.lengthSq();if(e===0)return this.set(0,0,0);let i=t.dot(this)/e;return this.copy(t).multiplyScalar(i)}projectOnPlane(t){return Bi.copy(this).projectOnVector(t),this.sub(Bi)}reflect(t){return this.sub(Bi.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let i=this.dot(t)/e;return Math.acos(j(i,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,i=this.y-t.y,s=this.z-t.z;return e*e+i*i+s*s}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,i){let s=Math.sin(e)*t;return this.x=s*Math.sin(i),this.y=Math.cos(e)*t,this.z=s*Math.cos(i),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,i){return this.x=t*Math.sin(e),this.y=i,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){let e=this.setFromMatrixColumn(t,0).length(),i=this.setFromMatrixColumn(t,1).length(),s=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=i,this.z=s,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let t=Math.random()*Math.PI*2,e=Math.random()*2-1,i=Math.sqrt(1-e*e);return this.x=i*Math.cos(t),this.y=e,this.z=i*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},Bi=new V,Tr=new qt,Y=class n{static{p(this,"Matrix3")}static{n.prototype.isMatrix3=!0}constructor(t,e,i,s,r,o,a,c,l){this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,i,s,r,o,a,c,l)}set(t,e,i,s,r,o,a,c,l){let u=this.elements;return u[0]=t,u[1]=s,u[2]=a,u[3]=e,u[4]=r,u[5]=c,u[6]=i,u[7]=o,u[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){let e=this.elements,i=t.elements;return e[0]=i[0],e[1]=i[1],e[2]=i[2],e[3]=i[3],e[4]=i[4],e[5]=i[5],e[6]=i[6],e[7]=i[7],e[8]=i[8],this}extractBasis(t,e,i){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),i.setFromMatrix3Column(this,2),this}setFromMatrix4(t){let e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let i=t.elements,s=e.elements,r=this.elements,o=i[0],a=i[3],c=i[6],l=i[1],u=i[4],h=i[7],f=i[2],d=i[5],m=i[8],g=s[0],_=s[3],x=s[6],v=s[1],y=s[4],b=s[7],S=s[2],A=s[5],M=s[8];return r[0]=o*g+a*v+c*S,r[3]=o*_+a*y+c*A,r[6]=o*x+a*b+c*M,r[1]=l*g+u*v+h*S,r[4]=l*_+u*y+h*A,r[7]=l*x+u*b+h*M,r[2]=f*g+d*v+m*S,r[5]=f*_+d*y+m*A,r[8]=f*x+d*b+m*M,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8];return e*o*u-e*a*l-i*r*u+i*a*c+s*r*l-s*o*c}invert(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=u*o-a*l,f=a*c-u*r,d=l*r-o*c,m=e*h+i*f+s*d;if(m===0)return this.set(0,0,0,0,0,0,0,0,0);let g=1/m;return t[0]=h*g,t[1]=(s*l-u*i)*g,t[2]=(a*i-s*o)*g,t[3]=f*g,t[4]=(u*e-s*c)*g,t[5]=(s*r-a*e)*g,t[6]=d*g,t[7]=(i*c-l*e)*g,t[8]=(o*e-i*r)*g,this}transpose(){let t,e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){let e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,i,s,r,o,a){let c=Math.cos(r),l=Math.sin(r);return this.set(i*c,i*l,-i*(c*o+l*a)+o+t,-s*l,s*c,-s*(-l*o+c*a)+a+e,0,0,1),this}scale(t,e){return He("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(zi.makeScale(t,e)),this}rotate(t){return He("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(zi.makeRotation(-t)),this}translate(t,e){return He("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(zi.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,-i,0,i,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){let e=this.elements,i=t.elements;for(let s=0;s<9;s++)if(e[s]!==i[s])return!1;return!0}fromArray(t,e=0){for(let i=0;i<9;i++)this.elements[i]=t[i+e];return this}toArray(t=[],e=0){let i=this.elements;return t[e]=i[0],t[e+1]=i[1],t[e+2]=i[2],t[e+3]=i[3],t[e+4]=i[4],t[e+5]=i[5],t[e+6]=i[6],t[e+7]=i[7],t[e+8]=i[8],t}clone(){return new this.constructor().fromArray(this.elements)}},zi=new Y,wr=new Y().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Er=new Y().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function sc(){let n={enabled:!0,workingColorSpace:as,spaces:{},convert:p(function(s,r,o){return this.enabled===!1||r===o||!r||!o||(this.spaces[r].transfer===Kn&&(s.r=Qt(s.r),s.g=Qt(s.g),s.b=Qt(s.b)),this.spaces[r].primaries!==this.spaces[o].primaries&&(s.applyMatrix3(this.spaces[r].toXYZ),s.applyMatrix3(this.spaces[o].fromXYZ)),this.spaces[o].transfer===Kn&&(s.r=We(s.r),s.g=We(s.g),s.b=We(s.b))),s},"convert"),workingToColorSpace:p(function(s,r){return this.convert(s,this.workingColorSpace,r)},"workingToColorSpace"),colorSpaceToWorking:p(function(s,r){return this.convert(s,r,this.workingColorSpace)},"colorSpaceToWorking"),getPrimaries:p(function(s){return this.spaces[s].primaries},"getPrimaries"),getTransfer:p(function(s){return s===Es?cs:this.spaces[s].transfer},"getTransfer"),getToneMappingMode:p(function(s){return this.spaces[s].outputColorSpaceConfig.toneMappingMode||"standard"},"getToneMappingMode"),getLuminanceCoefficients:p(function(s,r=this.workingColorSpace){return s.fromArray(this.spaces[r].luminanceCoefficients)},"getLuminanceCoefficients"),define:p(function(s){Object.assign(this.spaces,s)},"define"),_getMatrix:p(function(s,r,o){return s.copy(this.spaces[r].toXYZ).multiply(this.spaces[o].fromXYZ)},"_getMatrix"),_getDrawingBufferColorSpace:p(function(s){return this.spaces[s].outputColorSpaceConfig.drawingBufferColorSpace},"_getDrawingBufferColorSpace"),_getUnpackColorSpace:p(function(s=this.workingColorSpace){return this.spaces[s].workingColorSpaceConfig.unpackColorSpace},"_getUnpackColorSpace"),fromWorkingColorSpace:p(function(s,r){return He("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),n.workingToColorSpace(s,r)},"fromWorkingColorSpace"),toWorkingColorSpace:p(function(s,r){return He("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),n.colorSpaceToWorking(s,r)},"toWorkingColorSpace")},t=[.64,.33,.3,.6,.15,.06],e=[.2126,.7152,.0722],i=[.3127,.329];return n.define({[as]:{primaries:t,whitePoint:i,transfer:cs,toXYZ:wr,fromXYZ:Er,luminanceCoefficients:e,workingColorSpaceConfig:{unpackColorSpace:kt},outputColorSpaceConfig:{drawingBufferColorSpace:kt}},[kt]:{primaries:t,whitePoint:i,transfer:Kn,toXYZ:wr,fromXYZ:Er,luminanceCoefficients:e,outputColorSpaceConfig:{drawingBufferColorSpace:kt}}}),n}p(sc,"createColorManagement");var zt=sc();function Qt(n){return n<.04045?n*.0773993808:Math.pow(n*.9478672986+.0521327014,2.4)}p(Qt,"SRGBToLinear");function We(n){return n<.0031308?n*12.92:1.055*Math.pow(n,.41666)-.055}p(We,"LinearToSRGB");var Ue,ti=class{static{p(this,"ImageUtils")}static getDataURL(t,e="image/png"){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let i;if(t instanceof HTMLCanvasElement)i=t;else{Ue===void 0&&(Ue=hs("canvas")),Ue.width=t.width,Ue.height=t.height;let s=Ue.getContext("2d");t instanceof ImageData?s.putImageData(t,0,0):s.drawImage(t,0,0,t.width,t.height),i=Ue}return i.toDataURL(e)}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){let e=hs("canvas");e.width=t.width,e.height=t.height;let i=e.getContext("2d");i.drawImage(t,0,0,t.width,t.height);let s=i.getImageData(0,0,t.width,t.height),r=s.data;for(let o=0;o<r.length;o++)r[o]=Qt(r[o]/255)*255;return i.putImageData(s,0,0),e}else if(t.data){let e=t.data.slice(0);for(let i=0;i<e.length;i++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[i]=Math.floor(Qt(e[i]/255)*255):e[i]=Qt(e[i]);return{data:e,width:t.width,height:t.height}}else return pt("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}},rc=0,ei=class{static{p(this,"Source")}constructor(t=null){this.isSource=!0,Object.defineProperty(this,"id",{value:rc++}),this.uuid=gi(),this.data=t,this.dataReady=!0,this.version=0}getSize(t){let e=this.data;return typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement?t.set(e.videoWidth,e.videoHeight,0):typeof VideoFrame<"u"&&e instanceof VideoFrame?t.set(e.displayWidth,e.displayHeight,0):e!==null?t.set(e.width,e.height,e.depth||0):t.set(0,0,0),t}set needsUpdate(t){t===!0&&this.version++}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];let i={uuid:this.uuid,url:""},s=this.data;if(s!==null){let r;if(Array.isArray(s)){r=[];for(let o=0,a=s.length;o<a;o++)s[o].isDataTexture?r.push(ki(s[o].image)):r.push(ki(s[o]))}else r=ki(s);i.url=r}return e||(t.images[this.uuid]=i),i}};function ki(n){return typeof HTMLImageElement<"u"&&n instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&n instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&n instanceof ImageBitmap?ti.getDataURL(n):n.data?{data:Array.from(n.data),width:n.width,height:n.height,type:n.data.constructor.name}:(pt("Texture: Unable to serialize Texture."),{})}p(ki,"serializeImage");var oc=0,Vi=new V,Xe=class n extends Me{static{p(this,"Texture")}constructor(t=n.DEFAULT_IMAGE,e=n.DEFAULT_MAPPING,i=pn,s=pn,r=qr,o=$r,a=Jr,c=Yr,l=n.DEFAULT_ANISOTROPY,u=Es){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:oc++}),this.uuid=gi(),this.name="",this.source=new ei(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=i,this.wrapT=s,this.magFilter=r,this.minFilter=o,this.anisotropy=l,this.format=a,this.internalFormat=null,this.type=c,this.offset=new mt(0,0),this.repeat=new mt(1,1),this.center=new mt(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Y,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=u,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(Vi).x}get height(){return this.source.getSize(Vi).y}get depth(){return this.source.getSize(Vi).z}get image(){return this.source.data}set image(t){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.normalized=t.normalized,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.renderTarget=t.renderTarget,this.isRenderTargetTexture=t.isRenderTargetTexture,this.isArrayTexture=t.isArrayTexture,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}setValues(t){for(let e in t){let i=t[e];if(i===void 0){pt(`Texture.setValues(): parameter '${e}' has value of undefined.`);continue}let s=this[e];if(s===void 0){pt(`Texture.setValues(): property '${e}' does not exist.`);continue}s&&i&&s.isVector2&&i.isVector2||s&&i&&s.isVector3&&i.isVector3||s&&i&&s.isMatrix3&&i.isMatrix3?s.copy(i):this[e]=i}}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];let i={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(i.userData=this.userData),e||(t.textures[this.uuid]=i),i}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==Ts)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case es:t.x=t.x-Math.floor(t.x);break;case pn:t.x=t.x<0?0:1;break;case ns:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case es:t.y=t.y-Math.floor(t.y);break;case pn:t.y=t.y<0?0:1;break;case ns:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}};Xe.DEFAULT_IMAGE=null;Xe.DEFAULT_MAPPING=Ts;Xe.DEFAULT_ANISOTROPY=1;var fs=class n{static{p(this,"Vector4")}static{n.prototype.isVector4=!0}constructor(t=0,e=0,i=0,s=1){this.x=t,this.y=e,this.z=i,this.w=s}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,i,s){return this.x=t,this.y=e,this.z=i,this.w=s,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("THREE.Vector4: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){let e=this.x,i=this.y,s=this.z,r=this.w,o=t.elements;return this.x=o[0]*e+o[4]*i+o[8]*s+o[12]*r,this.y=o[1]*e+o[5]*i+o[9]*s+o[13]*r,this.z=o[2]*e+o[6]*i+o[10]*s+o[14]*r,this.w=o[3]*e+o[7]*i+o[11]*s+o[15]*r,this}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this.w/=t.w,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);let e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,i,s,r,c=t.elements,l=c[0],u=c[4],h=c[8],f=c[1],d=c[5],m=c[9],g=c[2],_=c[6],x=c[10];if(Math.abs(u-f)<.01&&Math.abs(h-g)<.01&&Math.abs(m-_)<.01){if(Math.abs(u+f)<.1&&Math.abs(h+g)<.1&&Math.abs(m+_)<.1&&Math.abs(l+d+x-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;let y=(l+1)/2,b=(d+1)/2,S=(x+1)/2,A=(u+f)/4,M=(h+g)/4,T=(m+_)/4;return y>b&&y>S?y<.01?(i=0,s=.707106781,r=.707106781):(i=Math.sqrt(y),s=A/i,r=M/i):b>S?b<.01?(i=.707106781,s=0,r=.707106781):(s=Math.sqrt(b),i=A/s,r=T/s):S<.01?(i=.707106781,s=.707106781,r=0):(r=Math.sqrt(S),i=M/r,s=T/r),this.set(i,s,r,e),this}let v=Math.sqrt((_-m)*(_-m)+(h-g)*(h-g)+(f-u)*(f-u));return Math.abs(v)<.001&&(v=1),this.x=(_-m)/v,this.y=(h-g)/v,this.z=(f-u)/v,this.w=Math.acos((l+d+x-1)/2),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=j(this.x,t.x,e.x),this.y=j(this.y,t.y,e.y),this.z=j(this.z,t.z,e.z),this.w=j(this.w,t.w,e.w),this}clampScalar(t,e){return this.x=j(this.x,t,e),this.y=j(this.y,t,e),this.z=j(this.z,t,e),this.w=j(this.w,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(j(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this.z=t.z+(e.z-t.z)*i,this.w=t.w+(e.w-t.w)*i,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};var gt=class n{static{p(this,"Matrix4")}static{n.prototype.isMatrix4=!0}constructor(t,e,i,s,r,o,a,c,l,u,h,f,d,m,g,_){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,i,s,r,o,a,c,l,u,h,f,d,m,g,_)}set(t,e,i,s,r,o,a,c,l,u,h,f,d,m,g,_){let x=this.elements;return x[0]=t,x[4]=e,x[8]=i,x[12]=s,x[1]=r,x[5]=o,x[9]=a,x[13]=c,x[2]=l,x[6]=u,x[10]=h,x[14]=f,x[3]=d,x[7]=m,x[11]=g,x[15]=_,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new n().fromArray(this.elements)}copy(t){let e=this.elements,i=t.elements;return e[0]=i[0],e[1]=i[1],e[2]=i[2],e[3]=i[3],e[4]=i[4],e[5]=i[5],e[6]=i[6],e[7]=i[7],e[8]=i[8],e[9]=i[9],e[10]=i[10],e[11]=i[11],e[12]=i[12],e[13]=i[13],e[14]=i[14],e[15]=i[15],this}copyPosition(t){let e=this.elements,i=t.elements;return e[12]=i[12],e[13]=i[13],e[14]=i[14],this}setFromMatrix3(t){let e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,i){return this.determinantAffine()===0?(t.set(1,0,0),e.set(0,1,0),i.set(0,0,1),this):(t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),i.setFromMatrixColumn(this,2),this)}makeBasis(t,e,i){return this.set(t.x,e.x,i.x,0,t.y,e.y,i.y,0,t.z,e.z,i.z,0,0,0,0,1),this}extractRotation(t){if(t.determinantAffine()===0)return this.identity();let e=this.elements,i=t.elements,s=1/Fe.setFromMatrixColumn(t,0).length(),r=1/Fe.setFromMatrixColumn(t,1).length(),o=1/Fe.setFromMatrixColumn(t,2).length();return e[0]=i[0]*s,e[1]=i[1]*s,e[2]=i[2]*s,e[3]=0,e[4]=i[4]*r,e[5]=i[5]*r,e[6]=i[6]*r,e[7]=0,e[8]=i[8]*o,e[9]=i[9]*o,e[10]=i[10]*o,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){let e=this.elements,i=t.x,s=t.y,r=t.z,o=Math.cos(i),a=Math.sin(i),c=Math.cos(s),l=Math.sin(s),u=Math.cos(r),h=Math.sin(r);if(t.order==="XYZ"){let f=o*u,d=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=-c*h,e[8]=l,e[1]=d+m*l,e[5]=f-g*l,e[9]=-a*c,e[2]=g-f*l,e[6]=m+d*l,e[10]=o*c}else if(t.order==="YXZ"){let f=c*u,d=c*h,m=l*u,g=l*h;e[0]=f+g*a,e[4]=m*a-d,e[8]=o*l,e[1]=o*h,e[5]=o*u,e[9]=-a,e[2]=d*a-m,e[6]=g+f*a,e[10]=o*c}else if(t.order==="ZXY"){let f=c*u,d=c*h,m=l*u,g=l*h;e[0]=f-g*a,e[4]=-o*h,e[8]=m+d*a,e[1]=d+m*a,e[5]=o*u,e[9]=g-f*a,e[2]=-o*l,e[6]=a,e[10]=o*c}else if(t.order==="ZYX"){let f=o*u,d=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=m*l-d,e[8]=f*l+g,e[1]=c*h,e[5]=g*l+f,e[9]=d*l-m,e[2]=-l,e[6]=a*c,e[10]=o*c}else if(t.order==="YZX"){let f=o*c,d=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=g-f*h,e[8]=m*h+d,e[1]=h,e[5]=o*u,e[9]=-a*u,e[2]=-l*u,e[6]=d*h+m,e[10]=f-g*h}else if(t.order==="XZY"){let f=o*c,d=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=-h,e[8]=l*u,e[1]=f*h+g,e[5]=o*u,e[9]=d*h-m,e[2]=m*h-d,e[6]=a*u,e[10]=g*h+f}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(ac,t,cc)}lookAt(t,e,i){let s=this.elements;return Pt.subVectors(t,e),Pt.lengthSq()===0&&(Pt.z=1),Pt.normalize(),re.crossVectors(i,Pt),re.lengthSq()===0&&(Math.abs(i.z)===1?Pt.x+=1e-4:Pt.z+=1e-4,Pt.normalize(),re.crossVectors(i,Pt)),re.normalize(),kn.crossVectors(Pt,re),s[0]=re.x,s[4]=kn.x,s[8]=Pt.x,s[1]=re.y,s[5]=kn.y,s[9]=Pt.y,s[2]=re.z,s[6]=kn.z,s[10]=Pt.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let i=t.elements,s=e.elements,r=this.elements,o=i[0],a=i[4],c=i[8],l=i[12],u=i[1],h=i[5],f=i[9],d=i[13],m=i[2],g=i[6],_=i[10],x=i[14],v=i[3],y=i[7],b=i[11],S=i[15],A=s[0],M=s[4],T=s[8],I=s[12],E=s[1],N=s[5],L=s[9],R=s[13],C=s[2],P=s[6],w=s[10],U=s[14],F=s[3],D=s[7],O=s[11],k=s[15];return r[0]=o*A+a*E+c*C+l*F,r[4]=o*M+a*N+c*P+l*D,r[8]=o*T+a*L+c*w+l*O,r[12]=o*I+a*R+c*U+l*k,r[1]=u*A+h*E+f*C+d*F,r[5]=u*M+h*N+f*P+d*D,r[9]=u*T+h*L+f*w+d*O,r[13]=u*I+h*R+f*U+d*k,r[2]=m*A+g*E+_*C+x*F,r[6]=m*M+g*N+_*P+x*D,r[10]=m*T+g*L+_*w+x*O,r[14]=m*I+g*R+_*U+x*k,r[3]=v*A+y*E+b*C+S*F,r[7]=v*M+y*N+b*P+S*D,r[11]=v*T+y*L+b*w+S*O,r[15]=v*I+y*R+b*U+S*k,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){let t=this.elements,e=t[0],i=t[4],s=t[8],r=t[12],o=t[1],a=t[5],c=t[9],l=t[13],u=t[2],h=t[6],f=t[10],d=t[14],m=t[3],g=t[7],_=t[11],x=t[15],v=c*d-l*f,y=a*d-l*h,b=a*f-c*h,S=o*d-l*u,A=o*f-c*u,M=o*h-a*u;return e*(g*v-_*y+x*b)-i*(m*v-_*S+x*A)+s*(m*y-g*S+x*M)-r*(m*b-g*A+_*M)}determinantAffine(){let t=this.elements,e=t[0],i=t[4],s=t[8],r=t[1],o=t[5],a=t[9],c=t[2],l=t[6],u=t[10];return e*(o*u-a*l)-i*(r*u-a*c)+s*(r*l-o*c)}transpose(){let t=this.elements,e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,i){let s=this.elements;return t.isVector3?(s[12]=t.x,s[13]=t.y,s[14]=t.z):(s[12]=t,s[13]=e,s[14]=i),this}invert(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=t[9],f=t[10],d=t[11],m=t[12],g=t[13],_=t[14],x=t[15],v=e*a-i*o,y=e*c-s*o,b=e*l-r*o,S=i*c-s*a,A=i*l-r*a,M=s*l-r*c,T=u*g-h*m,I=u*_-f*m,E=u*x-d*m,N=h*_-f*g,L=h*x-d*g,R=f*x-d*_,C=v*R-y*L+b*N+S*E-A*I+M*T;if(C===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let P=1/C;return t[0]=(a*R-c*L+l*N)*P,t[1]=(s*L-i*R-r*N)*P,t[2]=(g*M-_*A+x*S)*P,t[3]=(f*A-h*M-d*S)*P,t[4]=(c*E-o*R-l*I)*P,t[5]=(e*R-s*E+r*I)*P,t[6]=(_*b-m*M-x*y)*P,t[7]=(u*M-f*b+d*y)*P,t[8]=(o*L-a*E+l*T)*P,t[9]=(i*E-e*L-r*T)*P,t[10]=(m*A-g*b+x*v)*P,t[11]=(h*b-u*A-d*v)*P,t[12]=(a*I-o*N-c*T)*P,t[13]=(e*N-i*I+s*T)*P,t[14]=(g*y-m*S-_*v)*P,t[15]=(u*S-h*y+f*v)*P,this}scale(t){let e=this.elements,i=t.x,s=t.y,r=t.z;return e[0]*=i,e[4]*=s,e[8]*=r,e[1]*=i,e[5]*=s,e[9]*=r,e[2]*=i,e[6]*=s,e[10]*=r,e[3]*=i,e[7]*=s,e[11]*=r,this}getMaxScaleOnAxis(){let t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],i=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],s=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,i,s))}makeTranslation(t,e,i){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,i,0,0,0,1),this}makeRotationX(t){let e=Math.cos(t),i=Math.sin(t);return this.set(1,0,0,0,0,e,-i,0,0,i,e,0,0,0,0,1),this}makeRotationY(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,0,i,0,0,1,0,0,-i,0,e,0,0,0,0,1),this}makeRotationZ(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,-i,0,0,i,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){let i=Math.cos(e),s=Math.sin(e),r=1-i,o=t.x,a=t.y,c=t.z,l=r*o,u=r*a;return this.set(l*o+i,l*a-s*c,l*c+s*a,0,l*a+s*c,u*a+i,u*c-s*o,0,l*c-s*a,u*c+s*o,r*c*c+i,0,0,0,0,1),this}makeScale(t,e,i){return this.set(t,0,0,0,0,e,0,0,0,0,i,0,0,0,0,1),this}makeShear(t,e,i,s,r,o){return this.set(1,i,r,0,t,1,o,0,e,s,1,0,0,0,0,1),this}compose(t,e,i){let s=this.elements,r=e._x,o=e._y,a=e._z,c=e._w,l=r+r,u=o+o,h=a+a,f=r*l,d=r*u,m=r*h,g=o*u,_=o*h,x=a*h,v=c*l,y=c*u,b=c*h,S=i.x,A=i.y,M=i.z;return s[0]=(1-(g+x))*S,s[1]=(d+b)*S,s[2]=(m-y)*S,s[3]=0,s[4]=(d-b)*A,s[5]=(1-(f+x))*A,s[6]=(_+v)*A,s[7]=0,s[8]=(m+y)*M,s[9]=(_-v)*M,s[10]=(1-(f+g))*M,s[11]=0,s[12]=t.x,s[13]=t.y,s[14]=t.z,s[15]=1,this}decompose(t,e,i){let s=this.elements;t.x=s[12],t.y=s[13],t.z=s[14];let r=this.determinantAffine();if(r===0)return i.set(1,1,1),e.identity(),this;let o=Fe.set(s[0],s[1],s[2]).length(),a=Fe.set(s[4],s[5],s[6]).length(),c=Fe.set(s[8],s[9],s[10]).length();r<0&&(o=-o),Wt.copy(this);let l=1/o,u=1/a,h=1/c;return Wt.elements[0]*=l,Wt.elements[1]*=l,Wt.elements[2]*=l,Wt.elements[4]*=u,Wt.elements[5]*=u,Wt.elements[6]*=u,Wt.elements[8]*=h,Wt.elements[9]*=h,Wt.elements[10]*=h,e.setFromRotationMatrix(Wt),i.x=o,i.y=a,i.z=c,this}makePerspective(t,e,i,s,r,o,a=mn,c=!1){let l=this.elements,u=2*r/(e-t),h=2*r/(i-s),f=(e+t)/(e-t),d=(i+s)/(i-s),m,g;if(c)m=r/(o-r),g=o*r/(o-r);else if(a===mn)m=-(o+r)/(o-r),g=-2*o*r/(o-r);else if(a===us)m=-o/(o-r),g=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=h,l[9]=d,l[13]=0,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,i,s,r,o,a=mn,c=!1){let l=this.elements,u=2/(e-t),h=2/(i-s),f=-(e+t)/(e-t),d=-(i+s)/(i-s),m,g;if(c)m=1/(o-r),g=o/(o-r);else if(a===mn)m=-2/(o-r),g=-(o+r)/(o-r);else if(a===us)m=-1/(o-r),g=-r/(o-r);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=h,l[9]=0,l[13]=d,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){let e=this.elements,i=t.elements;for(let s=0;s<16;s++)if(e[s]!==i[s])return!1;return!0}fromArray(t,e=0){for(let i=0;i<16;i++)this.elements[i]=t[i+e];return this}toArray(t=[],e=0){let i=this.elements;return t[e]=i[0],t[e+1]=i[1],t[e+2]=i[2],t[e+3]=i[3],t[e+4]=i[4],t[e+5]=i[5],t[e+6]=i[6],t[e+7]=i[7],t[e+8]=i[8],t[e+9]=i[9],t[e+10]=i[10],t[e+11]=i[11],t[e+12]=i[12],t[e+13]=i[13],t[e+14]=i[14],t[e+15]=i[15],t}},Fe=new V,Wt=new gt,ac=new V(0,0,0),cc=new V(1,1,1),re=new V,kn=new V,Pt=new V,Cr=new gt,Rr=new qt,_n=class n{static{p(this,"Euler")}constructor(t=0,e=0,i=0,s=n.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=i,this._order=s}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,i,s=this._order){return this._x=t,this._y=e,this._z=i,this._order=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,i=!0){let s=t.elements,r=s[0],o=s[4],a=s[8],c=s[1],l=s[5],u=s[9],h=s[2],f=s[6],d=s[10];switch(e){case"XYZ":this._y=Math.asin(j(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-u,d),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-j(u,-1,1)),Math.abs(u)<.9999999?(this._y=Math.atan2(a,d),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-h,r),this._z=0);break;case"ZXY":this._x=Math.asin(j(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-h,d),this._z=Math.atan2(-o,l)):(this._y=0,this._z=Math.atan2(c,r));break;case"ZYX":this._y=Math.asin(-j(h,-1,1)),Math.abs(h)<.9999999?(this._x=Math.atan2(f,d),this._z=Math.atan2(c,r)):(this._x=0,this._z=Math.atan2(-o,l));break;case"YZX":this._z=Math.asin(j(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-u,l),this._y=Math.atan2(-h,r)):(this._x=0,this._y=Math.atan2(a,d));break;case"XZY":this._z=Math.asin(-j(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-u,d),this._y=0);break;default:pt("Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,i===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,i){return Cr.makeRotationFromQuaternion(t),this.setFromRotationMatrix(Cr,e,i)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return Rr.setFromEuler(this),this.setFromQuaternion(Rr,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};_n.DEFAULT_ORDER="XYZ";var ni=class{static{p(this,"Layers")}constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}},lc=0,Ir=new V,Oe=new qt,Kt=new gt,Vn=new V,un=new V,uc=new V,hc=new qt,Pr=new V(1,0,0),Nr=new V(0,1,0),Lr=new V(0,0,1),Dr={type:"added"},fc={type:"removed"},Be={type:"childadded",child:null},Gi={type:"childremoved",child:null},be=class n extends Me{static{p(this,"Object3D")}constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:lc++}),this.uuid=gi(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=n.DEFAULT_UP.clone();let t=new V,e=new _n,i=new qt,s=new V(1,1,1);function r(){i.setFromEuler(e,!1)}p(r,"onRotationChange");function o(){e.setFromQuaternion(i,void 0,!1)}p(o,"onQuaternionChange"),e._onChange(r),i._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:i},scale:{configurable:!0,enumerable:!0,value:s},modelViewMatrix:{value:new gt},normalMatrix:{value:new Y}}),this.matrix=new gt,this.matrixWorld=new gt,this.matrixAutoUpdate=n.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=n.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new ni,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return Oe.setFromAxisAngle(t,e),this.quaternion.multiply(Oe),this}rotateOnWorldAxis(t,e){return Oe.setFromAxisAngle(t,e),this.quaternion.premultiply(Oe),this}rotateX(t){return this.rotateOnAxis(Pr,t)}rotateY(t){return this.rotateOnAxis(Nr,t)}rotateZ(t){return this.rotateOnAxis(Lr,t)}translateOnAxis(t,e){return Ir.copy(t).applyQuaternion(this.quaternion),this.position.add(Ir.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(Pr,t)}translateY(t){return this.translateOnAxis(Nr,t)}translateZ(t){return this.translateOnAxis(Lr,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(Kt.copy(this.matrixWorld).invert())}lookAt(t,e,i){t.isVector3?Vn.copy(t):Vn.set(t,e,i);let s=this.parent;this.updateWorldMatrix(!0,!1),un.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?Kt.lookAt(un,Vn,this.up):Kt.lookAt(Vn,un,this.up),this.quaternion.setFromRotationMatrix(Kt),s&&(Kt.extractRotation(s.matrixWorld),Oe.setFromRotationMatrix(Kt),this.quaternion.premultiply(Oe.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?(rt("Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(Dr),Be.child=t,this.dispatchEvent(Be),Be.child=null):rt("Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let i=0;i<arguments.length;i++)this.remove(arguments[i]);return this}let e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(fc),Gi.child=t,this.dispatchEvent(Gi),Gi.child=null),this}removeFromParent(){let t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),Kt.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),Kt.multiply(t.parent.matrixWorld)),t.applyMatrix4(Kt),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(Dr),Be.child=t,this.dispatchEvent(Be),Be.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let i=0,s=this.children.length;i<s;i++){let o=this.children[i].getObjectByProperty(t,e);if(o!==void 0)return o}}getObjectsByProperty(t,e,i=[]){this[t]===e&&i.push(this);let s=this.children;for(let r=0,o=s.length;r<o;r++)s[r].getObjectsByProperty(t,e,i);return i}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(un,t,uc),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(un,hc,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);let e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}traverse(t){t(this);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].traverseVisible(t)}traverseAncestors(t){let e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let t=this.pivot;if(t!==null){let e=t.x,i=t.y,s=t.z,r=this.matrix.elements;r[12]+=e-r[0]*e-r[4]*i-r[8]*s,r[13]+=i-r[1]*e-r[5]*i-r[9]*s,r[14]+=s-r[2]*e-r[6]*i-r[10]*s}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].updateMatrixWorld(t)}updateWorldMatrix(t,e,i=!1){let s=this.parent;if(t===!0&&s!==null&&s.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||i)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,i=!0),e===!0){let r=this.children;for(let o=0,a=r.length;o<a;o++)r[o].updateWorldMatrix(!1,!0,i)}}toJSON(t){let e=t===void 0||typeof t=="string",i={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},i.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let s={};s.uuid=this.uuid,s.type=this.type,this.name!==""&&(s.name=this.name),this.castShadow===!0&&(s.castShadow=!0),this.receiveShadow===!0&&(s.receiveShadow=!0),this.visible===!1&&(s.visible=!1),this.frustumCulled===!1&&(s.frustumCulled=!1),this.renderOrder!==0&&(s.renderOrder=this.renderOrder),this.static!==!1&&(s.static=this.static),Object.keys(this.userData).length>0&&(s.userData=this.userData),s.layers=this.layers.mask,s.matrix=this.matrix.toArray(),s.up=this.up.toArray(),this.pivot!==null&&(s.pivot=this.pivot.toArray()),this.matrixAutoUpdate===!1&&(s.matrixAutoUpdate=!1),this.morphTargetDictionary!==void 0&&(s.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(s.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(s.type="InstancedMesh",s.count=this.count,s.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(s.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(s.type="BatchedMesh",s.perObjectFrustumCulled=this.perObjectFrustumCulled,s.sortObjects=this.sortObjects,s.drawRanges=this._drawRanges,s.reservedRanges=this._reservedRanges,s.geometryInfo=this._geometryInfo.map(a=>({...a,boundingBox:a.boundingBox?a.boundingBox.toJSON():void 0,boundingSphere:a.boundingSphere?a.boundingSphere.toJSON():void 0})),s.instanceInfo=this._instanceInfo.map(a=>({...a})),s.availableInstanceIds=this._availableInstanceIds.slice(),s.availableGeometryIds=this._availableGeometryIds.slice(),s.nextIndexStart=this._nextIndexStart,s.nextVertexStart=this._nextVertexStart,s.geometryCount=this._geometryCount,s.maxInstanceCount=this._maxInstanceCount,s.maxVertexCount=this._maxVertexCount,s.maxIndexCount=this._maxIndexCount,s.geometryInitialized=this._geometryInitialized,s.matricesTexture=this._matricesTexture.toJSON(t),s.indirectTexture=this._indirectTexture.toJSON(t),this._colorsTexture!==null&&(s.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(s.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(s.boundingBox=this.boundingBox.toJSON()));function r(a,c){return a[c.uuid]===void 0&&(a[c.uuid]=c.toJSON(t)),c.uuid}if(p(r,"serialize"),this.isScene)this.background&&(this.background.isColor?s.background=this.background.toJSON():this.background.isTexture&&(s.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(s.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){s.geometry=r(t.geometries,this.geometry);let a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){let c=a.shapes;if(Array.isArray(c))for(let l=0,u=c.length;l<u;l++){let h=c[l];r(t.shapes,h)}else r(t.shapes,c)}}if(this.isSkinnedMesh&&(s.bindMode=this.bindMode,s.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),s.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let a=[];for(let c=0,l=this.material.length;c<l;c++)a.push(r(t.materials,this.material[c]));s.material=a}else s.material=r(t.materials,this.material);if(this.children.length>0){s.children=[];for(let a=0;a<this.children.length;a++)s.children.push(this.children[a].toJSON(t).object)}if(this.animations.length>0){s.animations=[];for(let a=0;a<this.animations.length;a++){let c=this.animations[a];s.animations.push(r(t.animations,c))}}if(e){let a=o(t.geometries),c=o(t.materials),l=o(t.textures),u=o(t.images),h=o(t.shapes),f=o(t.skeletons),d=o(t.animations),m=o(t.nodes);a.length>0&&(i.geometries=a),c.length>0&&(i.materials=c),l.length>0&&(i.textures=l),u.length>0&&(i.images=u),h.length>0&&(i.shapes=h),f.length>0&&(i.skeletons=f),d.length>0&&(i.animations=d),m.length>0&&(i.nodes=m)}return i.object=s,i;function o(a){let c=[];for(let l in a){let u=a[l];delete u.metadata,c.push(u)}return c}p(o,"extractFromCache")}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.pivot=t.pivot!==null?t.pivot.clone():null,this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.static=t.static,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let i=0;i<t.children.length;i++){let s=t.children[i];this.add(s.clone())}return this}};be.DEFAULT_UP=new V(0,1,0);be.DEFAULT_MATRIX_AUTO_UPDATE=!0;be.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var jr={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},oe={h:0,s:0,l:0},Gn={h:0,s:0,l:0};function Hi(n,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?n+(t-n)*6*e:e<1/2?t:e<2/3?n+(t-n)*6*(2/3-e):n}p(Hi,"hue2rgb");var xt=class{static{p(this,"Color")}constructor(t,e,i){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,i)}set(t,e,i){if(e===void 0&&i===void 0){let s=t;s&&s.isColor?this.copy(s):typeof s=="number"?this.setHex(s):typeof s=="string"&&this.setStyle(s)}else this.setRGB(t,e,i);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=kt){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,zt.colorSpaceToWorking(this,e),this}setRGB(t,e,i,s=zt.workingColorSpace){return this.r=t,this.g=e,this.b=i,zt.colorSpaceToWorking(this,s),this}setHSL(t,e,i,s=zt.workingColorSpace){if(t=ic(t,1),e=j(e,0,1),i=j(i,0,1),e===0)this.r=this.g=this.b=i;else{let r=i<=.5?i*(1+e):i+e-i*e,o=2*i-r;this.r=Hi(o,r,t+1/3),this.g=Hi(o,r,t),this.b=Hi(o,r,t-1/3)}return zt.colorSpaceToWorking(this,s),this}setStyle(t,e=kt){function i(r){r!==void 0&&parseFloat(r)<1&&pt("Color: Alpha component of "+t+" will be ignored.")}p(i,"handleAlpha");let s;if(s=/^(\w+)\(([^\)]*)\)/.exec(t)){let r,o=s[1],a=s[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:pt("Color: Unknown color model "+t)}}else if(s=/^\#([A-Fa-f\d]+)$/.exec(t)){let r=s[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(o===6)return this.setHex(parseInt(r,16),e);pt("Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=kt){let i=jr[t.toLowerCase()];return i!==void 0?this.setHex(i,e):pt("Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=Qt(t.r),this.g=Qt(t.g),this.b=Qt(t.b),this}copyLinearToSRGB(t){return this.r=We(t.r),this.g=We(t.g),this.b=We(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=kt){return zt.workingToColorSpace(Mt.copy(this),t),Math.round(j(Mt.r*255,0,255))*65536+Math.round(j(Mt.g*255,0,255))*256+Math.round(j(Mt.b*255,0,255))}getHexString(t=kt){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=zt.workingColorSpace){zt.workingToColorSpace(Mt.copy(this),e);let i=Mt.r,s=Mt.g,r=Mt.b,o=Math.max(i,s,r),a=Math.min(i,s,r),c,l,u=(a+o)/2;if(a===o)c=0,l=0;else{let h=o-a;switch(l=u<=.5?h/(o+a):h/(2-o-a),o){case i:c=(s-r)/h+(s<r?6:0);break;case s:c=(r-i)/h+2;break;case r:c=(i-s)/h+4;break}c/=6}return t.h=c,t.s=l,t.l=u,t}getRGB(t,e=zt.workingColorSpace){return zt.workingToColorSpace(Mt.copy(this),e),t.r=Mt.r,t.g=Mt.g,t.b=Mt.b,t}getStyle(t=kt){zt.workingToColorSpace(Mt.copy(this),t);let e=Mt.r,i=Mt.g,s=Mt.b;return t!==kt?`color(${t} ${e.toFixed(3)} ${i.toFixed(3)} ${s.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(i*255)},${Math.round(s*255)})`}offsetHSL(t,e,i){return this.getHSL(oe),this.setHSL(oe.h+t,oe.s+e,oe.l+i)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,i){return this.r=t.r+(e.r-t.r)*i,this.g=t.g+(e.g-t.g)*i,this.b=t.b+(e.b-t.b)*i,this}lerpHSL(t,e){this.getHSL(oe),t.getHSL(Gn);let i=Oi(oe.h,Gn.h,e),s=Oi(oe.s,Gn.s,e),r=Oi(oe.l,Gn.l,e);return this.setHSL(i,s,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){let e=this.r,i=this.g,s=this.b,r=t.elements;return this.r=r[0]*e+r[3]*i+r[6]*s,this.g=r[1]*e+r[4]*i+r[7]*s,this.b=r[2]*e+r[5]*i+r[8]*s,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},Mt=new xt;xt.NAMES=jr;var le=class{static{p(this,"Box3")}constructor(t=new V(1/0,1/0,1/0),e=new V(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=t,this.max=e}set(t,e){return this.min.copy(t),this.max.copy(e),this}setFromArray(t){this.makeEmpty();for(let e=0,i=t.length;e<i;e+=3)this.expandByPoint(Xt.fromArray(t,e));return this}setFromBufferAttribute(t){this.makeEmpty();for(let e=0,i=t.count;e<i;e++)this.expandByPoint(Xt.fromBufferAttribute(t,e));return this}setFromPoints(t){this.makeEmpty();for(let e=0,i=t.length;e<i;e++)this.expandByPoint(t[e]);return this}setFromCenterAndSize(t,e){let i=Xt.copy(e).multiplyScalar(.5);return this.min.copy(t).sub(i),this.max.copy(t).add(i),this}setFromObject(t,e=!1){return this.makeEmpty(),this.expandByObject(t,e)}clone(){return new this.constructor().copy(this)}copy(t){return this.min.copy(t.min),this.max.copy(t.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(t){return this.isEmpty()?t.set(0,0,0):t.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(t){return this.isEmpty()?t.set(0,0,0):t.subVectors(this.max,this.min)}expandByPoint(t){return this.min.min(t),this.max.max(t),this}expandByVector(t){return this.min.sub(t),this.max.add(t),this}expandByScalar(t){return this.min.addScalar(-t),this.max.addScalar(t),this}expandByObject(t,e=!1){t.updateWorldMatrix(!1,!1);let i=t.geometry;if(i!==void 0){let r=i.getAttribute("position");if(e===!0&&r!==void 0&&t.isInstancedMesh!==!0)for(let o=0,a=r.count;o<a;o++)t.isMesh===!0?t.getVertexPosition(o,Xt):Xt.fromBufferAttribute(r,o),Xt.applyMatrix4(t.matrixWorld),this.expandByPoint(Xt);else t.boundingBox!==void 0?(t.boundingBox===null&&t.computeBoundingBox(),Hn.copy(t.boundingBox)):(i.boundingBox===null&&i.computeBoundingBox(),Hn.copy(i.boundingBox)),Hn.applyMatrix4(t.matrixWorld),this.union(Hn)}let s=t.children;for(let r=0,o=s.length;r<o;r++)this.expandByObject(s[r],e);return this}containsPoint(t){return t.x>=this.min.x&&t.x<=this.max.x&&t.y>=this.min.y&&t.y<=this.max.y&&t.z>=this.min.z&&t.z<=this.max.z}containsBox(t){return this.min.x<=t.min.x&&t.max.x<=this.max.x&&this.min.y<=t.min.y&&t.max.y<=this.max.y&&this.min.z<=t.min.z&&t.max.z<=this.max.z}getParameter(t,e){return e.set((t.x-this.min.x)/(this.max.x-this.min.x),(t.y-this.min.y)/(this.max.y-this.min.y),(t.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(t){return t.max.x>=this.min.x&&t.min.x<=this.max.x&&t.max.y>=this.min.y&&t.min.y<=this.max.y&&t.max.z>=this.min.z&&t.min.z<=this.max.z}intersectsSphere(t){return this.clampPoint(t.center,Xt),Xt.distanceToSquared(t.center)<=t.radius*t.radius}intersectsPlane(t){let e,i;return t.normal.x>0?(e=t.normal.x*this.min.x,i=t.normal.x*this.max.x):(e=t.normal.x*this.max.x,i=t.normal.x*this.min.x),t.normal.y>0?(e+=t.normal.y*this.min.y,i+=t.normal.y*this.max.y):(e+=t.normal.y*this.max.y,i+=t.normal.y*this.min.y),t.normal.z>0?(e+=t.normal.z*this.min.z,i+=t.normal.z*this.max.z):(e+=t.normal.z*this.max.z,i+=t.normal.z*this.min.z),e<=-t.constant&&i>=-t.constant}intersectsTriangle(t){if(this.isEmpty())return!1;this.getCenter(hn),Wn.subVectors(this.max,hn),ze.subVectors(t.a,hn),ke.subVectors(t.b,hn),Ve.subVectors(t.c,hn),ae.subVectors(ke,ze),ce.subVectors(Ve,ke),ye.subVectors(ze,Ve);let e=[0,-ae.z,ae.y,0,-ce.z,ce.y,0,-ye.z,ye.y,ae.z,0,-ae.x,ce.z,0,-ce.x,ye.z,0,-ye.x,-ae.y,ae.x,0,-ce.y,ce.x,0,-ye.y,ye.x,0];return!Wi(e,ze,ke,Ve,Wn)||(e=[1,0,0,0,1,0,0,0,1],!Wi(e,ze,ke,Ve,Wn))?!1:(Xn.crossVectors(ae,ce),e=[Xn.x,Xn.y,Xn.z],Wi(e,ze,ke,Ve,Wn))}clampPoint(t,e){return e.copy(t).clamp(this.min,this.max)}distanceToPoint(t){return this.clampPoint(t,Xt).distanceTo(t)}getBoundingSphere(t){return this.isEmpty()?t.makeEmpty():(this.getCenter(t.center),t.radius=this.getSize(Xt).length()*.5),t}intersect(t){return this.min.max(t.min),this.max.min(t.max),this.isEmpty()&&this.makeEmpty(),this}union(t){return this.min.min(t.min),this.max.max(t.max),this}applyMatrix4(t){return this.isEmpty()?this:(jt[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(t),jt[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(t),jt[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(t),jt[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(t),jt[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(t),jt[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(t),jt[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(t),jt[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(t),this.setFromPoints(jt),this)}translate(t){return this.min.add(t),this.max.add(t),this}equals(t){return t.min.equals(this.min)&&t.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(t){return this.min.fromArray(t.min),this.max.fromArray(t.max),this}},jt=[new V,new V,new V,new V,new V,new V,new V,new V],Xt=new V,Hn=new le,ze=new V,ke=new V,Ve=new V,ae=new V,ce=new V,ye=new V,hn=new V,Wn=new V,Xn=new V,ve=new V;function Wi(n,t,e,i,s){for(let r=0,o=n.length-3;r<=o;r+=3){ve.fromArray(n,r);let a=s.x*Math.abs(ve.x)+s.y*Math.abs(ve.y)+s.z*Math.abs(ve.z),c=t.dot(ve),l=e.dot(ve),u=i.dot(ve);if(Math.max(-Math.max(c,l,u),Math.min(c,l,u))>a)return!1}return!0}p(Wi,"satForAxes");var lt=new V,qn=new mt,dc=0,Lt=class extends Me{static{p(this,"BufferAttribute")}constructor(t,e,i=!1){if(super(),Array.isArray(t))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:dc++}),this.name="",this.array=t,this.itemSize=e,this.count=t!==void 0?t.length/e:0,this.normalized=i,this.usage=ls,this.updateRanges=[],this.gpuType=Zr,this.version=0}onUploadCallback(){}set needsUpdate(t){t===!0&&this.version++}setUsage(t){return this.usage=t,this}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}copy(t){return this.name=t.name,this.array=new t.array.constructor(t.array),this.itemSize=t.itemSize,this.count=t.count,this.normalized=t.normalized,this.usage=t.usage,this.gpuType=t.gpuType,this}copyAt(t,e,i){t*=this.itemSize,i*=e.itemSize;for(let s=0,r=this.itemSize;s<r;s++)this.array[t+s]=e.array[i+s];return this}copyArray(t){return this.array.set(t),this}applyMatrix3(t){if(this.itemSize===2)for(let e=0,i=this.count;e<i;e++)qn.fromBufferAttribute(this,e),qn.applyMatrix3(t),this.setXY(e,qn.x,qn.y);else if(this.itemSize===3)for(let e=0,i=this.count;e<i;e++)lt.fromBufferAttribute(this,e),lt.applyMatrix3(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}applyMatrix4(t){for(let e=0,i=this.count;e<i;e++)lt.fromBufferAttribute(this,e),lt.applyMatrix4(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}applyNormalMatrix(t){for(let e=0,i=this.count;e<i;e++)lt.fromBufferAttribute(this,e),lt.applyNormalMatrix(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}transformDirection(t){for(let e=0,i=this.count;e<i;e++)lt.fromBufferAttribute(this,e),lt.transformDirection(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}set(t,e=0){return this.array.set(t,e),this}getComponent(t,e){let i=this.array[t*this.itemSize+e];return this.normalized&&(i=ln(i,this.array)),i}setComponent(t,e,i){return this.normalized&&(i=Tt(i,this.array)),this.array[t*this.itemSize+e]=i,this}getX(t){let e=this.array[t*this.itemSize];return this.normalized&&(e=ln(e,this.array)),e}setX(t,e){return this.normalized&&(e=Tt(e,this.array)),this.array[t*this.itemSize]=e,this}getY(t){let e=this.array[t*this.itemSize+1];return this.normalized&&(e=ln(e,this.array)),e}setY(t,e){return this.normalized&&(e=Tt(e,this.array)),this.array[t*this.itemSize+1]=e,this}getZ(t){let e=this.array[t*this.itemSize+2];return this.normalized&&(e=ln(e,this.array)),e}setZ(t,e){return this.normalized&&(e=Tt(e,this.array)),this.array[t*this.itemSize+2]=e,this}getW(t){let e=this.array[t*this.itemSize+3];return this.normalized&&(e=ln(e,this.array)),e}setW(t,e){return this.normalized&&(e=Tt(e,this.array)),this.array[t*this.itemSize+3]=e,this}setXY(t,e,i){return t*=this.itemSize,this.normalized&&(e=Tt(e,this.array),i=Tt(i,this.array)),this.array[t+0]=e,this.array[t+1]=i,this}setXYZ(t,e,i,s){return t*=this.itemSize,this.normalized&&(e=Tt(e,this.array),i=Tt(i,this.array),s=Tt(s,this.array)),this.array[t+0]=e,this.array[t+1]=i,this.array[t+2]=s,this}setXYZW(t,e,i,s,r){return t*=this.itemSize,this.normalized&&(e=Tt(e,this.array),i=Tt(i,this.array),s=Tt(s,this.array),r=Tt(r,this.array)),this.array[t+0]=e,this.array[t+1]=i,this.array[t+2]=s,this.array[t+3]=r,this}onUpload(t){return this.onUploadCallback=t,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let t={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(t.name=this.name),this.usage!==ls&&(t.usage=this.usage),t}dispose(){this.dispatchEvent({type:"dispose"})}};var ii=class extends Lt{static{p(this,"Uint16BufferAttribute")}constructor(t,e,i){super(new Uint16Array(t),e,i)}};var si=class extends Lt{static{p(this,"Uint32BufferAttribute")}constructor(t,e,i){super(new Uint32Array(t),e,i)}};var ue=class extends Lt{static{p(this,"Float32BufferAttribute")}constructor(t,e,i){super(new Float32Array(t),e,i)}},pc=new le,fn=new V,Xi=new V,ri=class{static{p(this,"Sphere")}constructor(t=new V,e=-1){this.isSphere=!0,this.center=t,this.radius=e}set(t,e){return this.center.copy(t),this.radius=e,this}setFromPoints(t,e){let i=this.center;e!==void 0?i.copy(e):pc.setFromPoints(t).getCenter(i);let s=0;for(let r=0,o=t.length;r<o;r++)s=Math.max(s,i.distanceToSquared(t[r]));return this.radius=Math.sqrt(s),this}copy(t){return this.center.copy(t.center),this.radius=t.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(t){return t.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(t){return t.distanceTo(this.center)-this.radius}intersectsSphere(t){let e=this.radius+t.radius;return t.center.distanceToSquared(this.center)<=e*e}intersectsBox(t){return t.intersectsSphere(this)}intersectsPlane(t){return Math.abs(t.distanceToPoint(this.center))<=this.radius}clampPoint(t,e){let i=this.center.distanceToSquared(t);return e.copy(t),i>this.radius*this.radius&&(e.sub(this.center).normalize(),e.multiplyScalar(this.radius).add(this.center)),e}getBoundingBox(t){return this.isEmpty()?(t.makeEmpty(),t):(t.set(this.center,this.center),t.expandByScalar(this.radius),t)}applyMatrix4(t){return this.center.applyMatrix4(t),this.radius=this.radius*t.getMaxScaleOnAxis(),this}translate(t){return this.center.add(t),this}expandByPoint(t){if(this.isEmpty())return this.center.copy(t),this.radius=0,this;fn.subVectors(t,this.center);let e=fn.lengthSq();if(e>this.radius*this.radius){let i=Math.sqrt(e),s=(i-this.radius)*.5;this.center.addScaledVector(fn,s/i),this.radius+=s}return this}union(t){return t.isEmpty()?this:this.isEmpty()?(this.copy(t),this):(this.center.equals(t.center)===!0?this.radius=Math.max(this.radius,t.radius):(Xi.subVectors(t.center,this.center).setLength(t.radius),this.expandByPoint(fn.copy(t.center).add(Xi)),this.expandByPoint(fn.copy(t.center).sub(Xi))),this)}equals(t){return t.center.equals(this.center)&&t.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(t){return this.radius=t.radius,this.center.fromArray(t.center),this}},mc=0,Bt=new gt,qi=new be,Ge=new V,Nt=new le,dn=new le,dt=new V,qe=class n extends Me{static{p(this,"BufferGeometry")}constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:mc++}),this.uuid=gi(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(t){return Array.isArray(t)?this.index=new(Qa(t)?si:ii)(t,1):this.index=t,this}setIndirect(t,e=0){return this.indirect=t,this.indirectOffset=e,this}getIndirect(){return this.indirect}getAttribute(t){return this.attributes[t]}setAttribute(t,e){return this.attributes[t]=e,this}deleteAttribute(t){return delete this.attributes[t],this}hasAttribute(t){return this.attributes[t]!==void 0}addGroup(t,e,i=0){this.groups.push({start:t,count:e,materialIndex:i})}clearGroups(){this.groups=[]}setDrawRange(t,e){this.drawRange.start=t,this.drawRange.count=e}applyMatrix4(t){let e=this.attributes.position;e!==void 0&&(e.applyMatrix4(t),e.needsUpdate=!0);let i=this.attributes.normal;if(i!==void 0){let r=new Y().getNormalMatrix(t);i.applyNormalMatrix(r),i.needsUpdate=!0}let s=this.attributes.tangent;return s!==void 0&&(s.transformDirection(t),s.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(t){return Bt.makeRotationFromQuaternion(t),this.applyMatrix4(Bt),this}rotateX(t){return Bt.makeRotationX(t),this.applyMatrix4(Bt),this}rotateY(t){return Bt.makeRotationY(t),this.applyMatrix4(Bt),this}rotateZ(t){return Bt.makeRotationZ(t),this.applyMatrix4(Bt),this}translate(t,e,i){return Bt.makeTranslation(t,e,i),this.applyMatrix4(Bt),this}scale(t,e,i){return Bt.makeScale(t,e,i),this.applyMatrix4(Bt),this}lookAt(t){return qi.lookAt(t),qi.updateMatrix(),this.applyMatrix4(qi.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(Ge).negate(),this.translate(Ge.x,Ge.y,Ge.z),this}setFromPoints(t){let e=this.getAttribute("position");if(e===void 0){let i=[];for(let s=0,r=t.length;s<r;s++){let o=t[s];i.push(o.x,o.y,o.z||0)}this.setAttribute("position",new ue(i,3))}else{let i=Math.min(t.length,e.count);for(let s=0;s<i;s++){let r=t[s];e.setXYZ(s,r.x,r.y,r.z||0)}t.length>e.count&&pt("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),e.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new le);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){rt("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new V(-1/0,-1/0,-1/0),new V(1/0,1/0,1/0));return}if(t!==void 0){if(this.boundingBox.setFromBufferAttribute(t),e)for(let i=0,s=e.length;i<s;i++){let r=e[i];Nt.setFromBufferAttribute(r),this.morphTargetsRelative?(dt.addVectors(this.boundingBox.min,Nt.min),this.boundingBox.expandByPoint(dt),dt.addVectors(this.boundingBox.max,Nt.max),this.boundingBox.expandByPoint(dt)):(this.boundingBox.expandByPoint(Nt.min),this.boundingBox.expandByPoint(Nt.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&rt('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new ri);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){rt("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new V,1/0);return}if(t){let i=this.boundingSphere.center;if(Nt.setFromBufferAttribute(t),e)for(let r=0,o=e.length;r<o;r++){let a=e[r];dn.setFromBufferAttribute(a),this.morphTargetsRelative?(dt.addVectors(Nt.min,dn.min),Nt.expandByPoint(dt),dt.addVectors(Nt.max,dn.max),Nt.expandByPoint(dt)):(Nt.expandByPoint(dn.min),Nt.expandByPoint(dn.max))}Nt.getCenter(i);let s=0;for(let r=0,o=t.count;r<o;r++)dt.fromBufferAttribute(t,r),s=Math.max(s,i.distanceToSquared(dt));if(e)for(let r=0,o=e.length;r<o;r++){let a=e[r],c=this.morphTargetsRelative;for(let l=0,u=a.count;l<u;l++)dt.fromBufferAttribute(a,l),c&&(Ge.fromBufferAttribute(t,l),dt.add(Ge)),s=Math.max(s,i.distanceToSquared(dt))}this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&rt('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let t=this.index,e=this.attributes;if(t===null||e.position===void 0||e.normal===void 0||e.uv===void 0){rt("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}let i=e.position,s=e.normal,r=e.uv,o=this.getAttribute("tangent");(o===void 0||o.count!==i.count)&&(o=new Lt(new Float32Array(4*i.count),4),this.setAttribute("tangent",o));let a=[],c=[];for(let T=0;T<i.count;T++)a[T]=new V,c[T]=new V;let l=new V,u=new V,h=new V,f=new mt,d=new mt,m=new mt,g=new V,_=new V;function x(T,I,E){l.fromBufferAttribute(i,T),u.fromBufferAttribute(i,I),h.fromBufferAttribute(i,E),f.fromBufferAttribute(r,T),d.fromBufferAttribute(r,I),m.fromBufferAttribute(r,E),u.sub(l),h.sub(l),d.sub(f),m.sub(f);let N=1/(d.x*m.y-m.x*d.y);isFinite(N)&&(g.copy(u).multiplyScalar(m.y).addScaledVector(h,-d.y).multiplyScalar(N),_.copy(h).multiplyScalar(d.x).addScaledVector(u,-m.x).multiplyScalar(N),a[T].add(g),a[I].add(g),a[E].add(g),c[T].add(_),c[I].add(_),c[E].add(_))}p(x,"handleTriangle");let v=this.groups;v.length===0&&(v=[{start:0,count:t.count}]);for(let T=0,I=v.length;T<I;++T){let E=v[T],N=E.start,L=E.count;for(let R=N,C=N+L;R<C;R+=3)x(t.getX(R+0),t.getX(R+1),t.getX(R+2))}let y=new V,b=new V,S=new V,A=new V;function M(T){S.fromBufferAttribute(s,T),A.copy(S);let I=a[T];y.copy(I),y.sub(S.multiplyScalar(S.dot(I))).normalize(),b.crossVectors(A,I);let N=b.dot(c[T])<0?-1:1;o.setXYZW(T,y.x,y.y,y.z,N)}p(M,"handleVertex");for(let T=0,I=v.length;T<I;++T){let E=v[T],N=E.start,L=E.count;for(let R=N,C=N+L;R<C;R+=3)M(t.getX(R+0)),M(t.getX(R+1)),M(t.getX(R+2))}this._transformed=!0}computeVertexNormals(){let t=this.index,e=this.getAttribute("position");if(e!==void 0){let i=this.getAttribute("normal");if(i===void 0||i.count!==e.count)i=new Lt(new Float32Array(e.count*3),3),this.setAttribute("normal",i);else for(let f=0,d=i.count;f<d;f++)i.setXYZ(f,0,0,0);let s=new V,r=new V,o=new V,a=new V,c=new V,l=new V,u=new V,h=new V;if(t)for(let f=0,d=t.count;f<d;f+=3){let m=t.getX(f+0),g=t.getX(f+1),_=t.getX(f+2);s.fromBufferAttribute(e,m),r.fromBufferAttribute(e,g),o.fromBufferAttribute(e,_),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),a.fromBufferAttribute(i,m),c.fromBufferAttribute(i,g),l.fromBufferAttribute(i,_),a.add(u),c.add(u),l.add(u),i.setXYZ(m,a.x,a.y,a.z),i.setXYZ(g,c.x,c.y,c.z),i.setXYZ(_,l.x,l.y,l.z)}else for(let f=0,d=e.count;f<d;f+=3)s.fromBufferAttribute(e,f+0),r.fromBufferAttribute(e,f+1),o.fromBufferAttribute(e,f+2),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),i.setXYZ(f+0,u.x,u.y,u.z),i.setXYZ(f+1,u.x,u.y,u.z),i.setXYZ(f+2,u.x,u.y,u.z);this.normalizeNormals(),i.needsUpdate=!0}}normalizeNormals(){let t=this.attributes.normal;for(let e=0,i=t.count;e<i;e++)dt.fromBufferAttribute(t,e),dt.normalize(),t.setXYZ(e,dt.x,dt.y,dt.z)}toNonIndexed(){function t(a,c){let l=a.array,u=a.itemSize,h=a.normalized,f=new l.constructor(c.length*u),d=0,m=0;for(let g=0,_=c.length;g<_;g++){a.isInterleavedBufferAttribute?d=c[g]*a.data.stride+a.offset:d=c[g]*u;for(let x=0;x<u;x++)f[m++]=l[d++]}return new Lt(f,u,h)}if(p(t,"convertBufferAttribute"),this.index===null)return pt("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let e=new n,i=this.index.array,s=this.attributes;for(let a in s){let c=s[a],l=t(c,i);e.setAttribute(a,l)}let r=this.morphAttributes;for(let a in r){let c=[],l=r[a];for(let u=0,h=l.length;u<h;u++){let f=l[u],d=t(f,i);c.push(d)}e.morphAttributes[a]=c}e.morphTargetsRelative=this.morphTargetsRelative;let o=this.groups;for(let a=0,c=o.length;a<c;a++){let l=o[a];e.addGroup(l.start,l.count,l.materialIndex)}return e}toJSON(){let t={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(t.uuid=this.uuid,t.type=this.parameters!==void 0&&this._transformed===!0?"BufferGeometry":this.type,this.name!==""&&(t.name=this.name),Object.keys(this.userData).length>0&&(t.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let c=this.parameters;for(let l in c)c[l]!==void 0&&(t[l]=c[l]);return t}t.data={attributes:{}};let e=this.index;e!==null&&(t.data.index={type:e.array.constructor.name,array:Array.prototype.slice.call(e.array)});let i=this.attributes;for(let c in i){let l=i[c];t.data.attributes[c]=l.toJSON(t.data)}let s={},r=!1;for(let c in this.morphAttributes){let l=this.morphAttributes[c],u=[];for(let h=0,f=l.length;h<f;h++){let d=l[h];u.push(d.toJSON(t.data))}u.length>0&&(s[c]=u,r=!0)}r&&(t.data.morphAttributes=s,t.data.morphTargetsRelative=this.morphTargetsRelative);let o=this.groups;o.length>0&&(t.data.groups=JSON.parse(JSON.stringify(o)));let a=this.boundingSphere;return a!==null&&(t.data.boundingSphere=a.toJSON()),t}clone(){return new this.constructor().copy(this)}copy(t){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let e={};this.name=t.name;let i=t.index;i!==null&&this.setIndex(i.clone());let s=t.attributes;for(let l in s){let u=s[l];this.setAttribute(l,u.clone(e))}let r=t.morphAttributes;for(let l in r){let u=[],h=r[l];for(let f=0,d=h.length;f<d;f++)u.push(h[f].clone(e));this.morphAttributes[l]=u}this.morphTargetsRelative=t.morphTargetsRelative;let o=t.groups;for(let l=0,u=o.length;l<u;l++){let h=o[l];this.addGroup(h.start,h.count,h.materialIndex)}let a=t.boundingBox;a!==null&&(this.boundingBox=a.clone());let c=t.boundingSphere;return c!==null&&(this.boundingSphere=c.clone()),this.drawRange.start=t.drawRange.start,this.drawRange.count=t.drawRange.count,this.userData=t.userData,this._transformed=t._transformed,this}dispose(){this.dispatchEvent({type:"dispose"})}};function gc(n,t,e=2){let i=t&&t.length,s=i?t[0]*e:n.length,r=Qr(n,0,s,e,!0),o=[];if(!r||r.next===r.prev)return o;let a,c,l;if(i&&(r=Mc(n,t,r,e)),n.length>80*e){a=n[0],c=n[1];let u=a,h=c;for(let f=e;f<s;f+=e){let d=n[f],m=n[f+1];d<a&&(a=d),m<c&&(c=m),d>u&&(u=d),m>h&&(h=m)}l=Math.max(u-a,h-c),l=l!==0?32767/l:0}return yn(r,o,e,a,c,l,0),o}p(gc,"earcut");function Qr(n,t,e,i,s){let r;if(s===Nc(n,t,e,i)>0)for(let o=t;o<e;o+=i)r=Ur(o/i|0,n[o],n[o+1],r);else for(let o=e-i;o>=t;o-=i)r=Ur(o/i|0,n[o],n[o+1],r);return r&&$e(r,r.next)&&(Mn(r),r=r.next),r}p(Qr,"linkedList");function Se(n,t){if(!n)return n;t||(t=n);let e=n,i;do if(i=!1,!e.steiner&&($e(e,e.next)||ot(e.prev,e,e.next)===0)){if(Mn(e),e=t=e.prev,e===e.next)break;i=!0}else e=e.next;while(i||e!==t);return t}p(Se,"filterPoints");function yn(n,t,e,i,s,r,o){if(!n)return;!o&&r&&wc(n,i,s,r);let a=n;for(;n.prev!==n.next;){let c=n.prev,l=n.next;if(r?_c(n,i,s,r):xc(n)){t.push(c.i,n.i,l.i),Mn(n),n=l.next,a=l.next;continue}if(n=l,n===a){o?o===1?(n=yc(Se(n),t),yn(n,t,e,i,s,r,2)):o===2&&vc(n,t,e,i,s,r):yn(Se(n),t,e,i,s,r,1);break}}}p(yn,"earcutLinked");function xc(n){let t=n.prev,e=n,i=n.next;if(ot(t,e,i)>=0)return!1;let s=t.x,r=e.x,o=i.x,a=t.y,c=e.y,l=i.y,u=Math.min(s,r,o),h=Math.min(a,c,l),f=Math.max(s,r,o),d=Math.max(a,c,l),m=i.next;for(;m!==t;){if(m.x>=u&&m.x<=f&&m.y>=h&&m.y<=d&&gn(s,a,r,c,o,l,m.x,m.y)&&ot(m.prev,m,m.next)>=0)return!1;m=m.next}return!0}p(xc,"isEar");function _c(n,t,e,i){let s=n.prev,r=n,o=n.next;if(ot(s,r,o)>=0)return!1;let a=s.x,c=r.x,l=o.x,u=s.y,h=r.y,f=o.y,d=Math.min(a,c,l),m=Math.min(u,h,f),g=Math.max(a,c,l),_=Math.max(u,h,f),x=ds(d,m,t,e,i),v=ds(g,_,t,e,i),y=n.prevZ,b=n.nextZ;for(;y&&y.z>=x&&b&&b.z<=v;){if(y.x>=d&&y.x<=g&&y.y>=m&&y.y<=_&&y!==s&&y!==o&&gn(a,u,c,h,l,f,y.x,y.y)&&ot(y.prev,y,y.next)>=0||(y=y.prevZ,b.x>=d&&b.x<=g&&b.y>=m&&b.y<=_&&b!==s&&b!==o&&gn(a,u,c,h,l,f,b.x,b.y)&&ot(b.prev,b,b.next)>=0))return!1;b=b.nextZ}for(;y&&y.z>=x;){if(y.x>=d&&y.x<=g&&y.y>=m&&y.y<=_&&y!==s&&y!==o&&gn(a,u,c,h,l,f,y.x,y.y)&&ot(y.prev,y,y.next)>=0)return!1;y=y.prevZ}for(;b&&b.z<=v;){if(b.x>=d&&b.x<=g&&b.y>=m&&b.y<=_&&b!==s&&b!==o&&gn(a,u,c,h,l,f,b.x,b.y)&&ot(b.prev,b,b.next)>=0)return!1;b=b.nextZ}return!0}p(_c,"isEarHashed");function yc(n,t){let e=n;do{let i=e.prev,s=e.next.next;!$e(i,s)&&eo(i,e,e.next,s)&&vn(i,s)&&vn(s,i)&&(t.push(i.i,e.i,s.i),Mn(e),Mn(e.next),e=n=s),e=e.next}while(e!==n);return Se(e)}p(yc,"cureLocalIntersections");function vc(n,t,e,i,s,r){let o=n;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&Rc(o,a)){let c=no(o,a);o=Se(o,o.next),c=Se(c,c.next),yn(o,t,e,i,s,r,0),yn(c,t,e,i,s,r,0);return}a=a.next}o=o.next}while(o!==n)}p(vc,"splitEarcut");function Mc(n,t,e,i){let s=[];for(let r=0,o=t.length;r<o;r++){let a=t[r]*i,c=r<o-1?t[r+1]*i:n.length,l=Qr(n,a,c,i,!1);l===l.next&&(l.steiner=!0),s.push(Cc(l))}s.sort(bc);for(let r=0;r<s.length;r++)e=Sc(s[r],e);return e}p(Mc,"eliminateHoles");function bc(n,t){let e=n.x-t.x;if(e===0&&(e=n.y-t.y,e===0)){let i=(n.next.y-n.y)/(n.next.x-n.x),s=(t.next.y-t.y)/(t.next.x-t.x);e=i-s}return e}p(bc,"compareXYSlope");function Sc(n,t){let e=Ac(n,t);if(!e)return t;let i=no(e,n);return Se(i,i.next),Se(e,e.next)}p(Sc,"eliminateHole");function Ac(n,t){let e=t,i=n.x,s=n.y,r=-1/0,o;if($e(n,e))return e;do{if($e(n,e.next))return e.next;if(s<=e.y&&s>=e.next.y&&e.next.y!==e.y){let h=e.x+(s-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(h<=i&&h>r&&(r=h,o=e.x<e.next.x?e:e.next,h===i))return o}e=e.next}while(e!==t);if(!o)return null;let a=o,c=o.x,l=o.y,u=1/0;e=o;do{if(i>=e.x&&e.x>=c&&i!==e.x&&to(s<l?i:r,s,c,l,s<l?r:i,s,e.x,e.y)){let h=Math.abs(s-e.y)/(i-e.x);vn(e,n)&&(h<u||h===u&&(e.x>o.x||e.x===o.x&&Tc(o,e)))&&(o=e,u=h)}e=e.next}while(e!==a);return o}p(Ac,"findHoleBridge");function Tc(n,t){return ot(n.prev,n,t.prev)<0&&ot(t.next,n,n.next)<0}p(Tc,"sectorContainsSector");function wc(n,t,e,i){let s=n;do s.z===0&&(s.z=ds(s.x,s.y,t,e,i)),s.prevZ=s.prev,s.nextZ=s.next,s=s.next;while(s!==n);s.prevZ.nextZ=null,s.prevZ=null,Ec(s)}p(wc,"indexCurve");function Ec(n){let t,e=1;do{let i=n,s;n=null;let r=null;for(t=0;i;){t++;let o=i,a=0;for(let l=0;l<e&&(a++,o=o.nextZ,!!o);l++);let c=e;for(;a>0||c>0&&o;)a!==0&&(c===0||!o||i.z<=o.z)?(s=i,i=i.nextZ,a--):(s=o,o=o.nextZ,c--),r?r.nextZ=s:n=s,s.prevZ=r,r=s;i=o}r.nextZ=null,e*=2}while(t>1);return n}p(Ec,"sortLinked");function ds(n,t,e,i,s){return n=(n-e)*s|0,t=(t-i)*s|0,n=(n|n<<8)&16711935,n=(n|n<<4)&252645135,n=(n|n<<2)&858993459,n=(n|n<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,n|t<<1}p(ds,"zOrder");function Cc(n){let t=n,e=n;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==n);return e}p(Cc,"getLeftmost");function to(n,t,e,i,s,r,o,a){return(s-o)*(t-a)>=(n-o)*(r-a)&&(n-o)*(i-a)>=(e-o)*(t-a)&&(e-o)*(r-a)>=(s-o)*(i-a)}p(to,"pointInTriangle");function gn(n,t,e,i,s,r,o,a){return!(n===o&&t===a)&&to(n,t,e,i,s,r,o,a)}p(gn,"pointInTriangleExceptFirst");function Rc(n,t){return n.next.i!==t.i&&n.prev.i!==t.i&&!Ic(n,t)&&(vn(n,t)&&vn(t,n)&&Pc(n,t)&&(ot(n.prev,n,t.prev)||ot(n,t.prev,t))||$e(n,t)&&ot(n.prev,n,n.next)>0&&ot(t.prev,t,t.next)>0)}p(Rc,"isValidDiagonal");function ot(n,t,e){return(t.y-n.y)*(e.x-t.x)-(t.x-n.x)*(e.y-t.y)}p(ot,"area");function $e(n,t){return n.x===t.x&&n.y===t.y}p($e,"equals");function eo(n,t,e,i){let s=Yn(ot(n,t,e)),r=Yn(ot(n,t,i)),o=Yn(ot(e,i,n)),a=Yn(ot(e,i,t));return!!(s!==r&&o!==a||s===0&&$n(n,e,t)||r===0&&$n(n,i,t)||o===0&&$n(e,n,i)||a===0&&$n(e,t,i))}p(eo,"intersects");function $n(n,t,e){return t.x<=Math.max(n.x,e.x)&&t.x>=Math.min(n.x,e.x)&&t.y<=Math.max(n.y,e.y)&&t.y>=Math.min(n.y,e.y)}p($n,"onSegment");function Yn(n){return n>0?1:n<0?-1:0}p(Yn,"sign");function Ic(n,t){let e=n;do{if(e.i!==n.i&&e.next.i!==n.i&&e.i!==t.i&&e.next.i!==t.i&&eo(e,e.next,n,t))return!0;e=e.next}while(e!==n);return!1}p(Ic,"intersectsPolygon");function vn(n,t){return ot(n.prev,n,n.next)<0?ot(n,t,n.next)>=0&&ot(n,n.prev,t)>=0:ot(n,t,n.prev)<0||ot(n,n.next,t)<0}p(vn,"locallyInside");function Pc(n,t){let e=n,i=!1,s=(n.x+t.x)/2,r=(n.y+t.y)/2;do e.y>r!=e.next.y>r&&e.next.y!==e.y&&s<(e.next.x-e.x)*(r-e.y)/(e.next.y-e.y)+e.x&&(i=!i),e=e.next;while(e!==n);return i}p(Pc,"middleInside");function no(n,t){let e=ps(n.i,n.x,n.y),i=ps(t.i,t.x,t.y),s=n.next,r=t.prev;return n.next=t,t.prev=n,e.next=s,s.prev=e,i.next=e,e.prev=i,r.next=i,i.prev=r,i}p(no,"splitPolygon");function Ur(n,t,e,i){let s=ps(n,t,e);return i?(s.next=i.next,s.prev=i,i.next.prev=s,i.next=s):(s.prev=s,s.next=s),s}p(Ur,"insertNode");function Mn(n){n.next.prev=n.prev,n.prev.next=n.next,n.prevZ&&(n.prevZ.nextZ=n.nextZ),n.nextZ&&(n.nextZ.prevZ=n.prevZ)}p(Mn,"removeNode");function ps(n,t,e){return{i:n,x:t,y:e,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}p(ps,"createNode");function Nc(n,t,e,i){let s=0;for(let r=t,o=e-i;r<e;r+=i)s+=(n[o]-n[r])*(n[r+1]+n[o+1]),o=r;return s}p(Nc,"signedArea");var ms=class{static{p(this,"Earcut")}static triangulate(t,e,i=2){return gc(t,e,i)}},bn=class n{static{p(this,"ShapeUtils")}static area(t){let e=t.length,i=0;for(let s=e-1,r=0;r<e;s=r++)i+=t[s].x*t[r].y-t[r].x*t[s].y;return i*.5}static isClockWise(t){return n.area(t)<0}static triangulateShape(t,e){let i=[],s=[],r=[];Fr(t),Or(i,t);let o=t.length;e.forEach(Fr);for(let c=0;c<e.length;c++)s.push(o),o+=e[c].length,Or(i,e[c]);let a=ms.triangulate(i,s);for(let c=0;c<a.length;c+=3)r.push(a.slice(c,c+3));return r}};function Fr(n){let t=n.length;t>2&&n[t-1].equals(n[0])&&n.pop()}p(Fr,"removeDupEndPts");function Or(n,t){for(let e=0;e<t.length;e++)n.push(t[e].x),n.push(t[e].y)}p(Or,"addContour");function io(n){let t={};for(let e in n){t[e]={};for(let i in n[e]){let s=n[e][i];if(Br(s))s.isRenderTargetTexture?(pt("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][i]=null):t[e][i]=s.clone();else if(Array.isArray(s))if(Br(s[0])){let r=[];for(let o=0,a=s.length;o<a;o++)r[o]=s[o].clone();t[e][i]=r}else t[e][i]=s.slice();else t[e][i]=s}}return t}p(io,"cloneUniforms");function bt(n){let t={};for(let e=0;e<n.length;e++){let i=io(n[e]);for(let s in i)t[s]=i[s]}return t}p(bt,"mergeUniforms");function Br(n){return n&&(n.isColor||n.isMatrix3||n.isMatrix4||n.isVector2||n.isVector3||n.isVector4||n.isTexture||n.isQuaternion)}p(Br,"isThreeObject");function Zn(n,t){return!n||n.constructor===t?n:typeof t.BYTES_PER_ELEMENT=="number"?new t(n):Array.prototype.slice.call(n)}p(Zn,"convertArray");var he=class{static{p(this,"Interpolant")}constructor(t,e,i,s){this.parameterPositions=t,this._cachedIndex=0,this.resultBuffer=s!==void 0?s:new e.constructor(i),this.sampleValues=e,this.valueSize=i,this.settings=null,this.DefaultSettings_={}}evaluate(t){let e=this.parameterPositions,i=this._cachedIndex,s=e[i],r=e[i-1];n:{t:{let o;e:{i:if(!(t<s)){for(let a=i+2;;){if(s===void 0){if(t<r)break i;return i=e.length,this._cachedIndex=i,this.copySampleValue_(i-1)}if(i===a)break;if(r=s,s=e[++i],t<s)break t}o=e.length;break e}if(!(t>=r)){let a=e[1];t<a&&(i=2,r=a);for(let c=i-2;;){if(r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(i===c)break;if(s=r,r=e[--i-1],t>=r)break t}o=i,i=0;break e}break n}for(;i<o;){let a=i+o>>>1;t<e[a]?o=a:i=a+1}if(s=e[i],r=e[i-1],r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(s===void 0)return i=e.length,this._cachedIndex=i,this.copySampleValue_(i-1)}this._cachedIndex=i,this.intervalChanged_(i,r,s)}return this.interpolate_(i,r,t,s)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(t){let e=this.resultBuffer,i=this.sampleValues,s=this.valueSize,r=t*s;for(let o=0;o!==s;++o)e[o]=i[r+o];return e}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},oi=class extends he{static{p(this,"CubicInterpolant")}constructor(t,e,i,s){super(t,e,i,s),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:ss,endingEnd:ss}}intervalChanged_(t,e,i){let s=this.parameterPositions,r=t-2,o=t+1,a=s[r],c=s[o];if(a===void 0)switch(this.getSettings_().endingStart){case rs:r=t,a=2*e-i;break;case os:r=s.length-2,a=e+s[r]-s[r+1];break;default:r=t,a=i}if(c===void 0)switch(this.getSettings_().endingEnd){case rs:o=t,c=2*i-e;break;case os:o=1,c=i+s[1]-s[0];break;default:o=t-1,c=e}let l=(i-e)*.5,u=this.valueSize;this._weightPrev=l/(e-a),this._weightNext=l/(c-i),this._offsetPrev=r*u,this._offsetNext=o*u}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this._offsetPrev,h=this._offsetNext,f=this._weightPrev,d=this._weightNext,m=(i-e)/(s-e),g=m*m,_=g*m,x=-f*_+2*f*g-f*m,v=(1+f)*_+(-1.5-2*f)*g+(-.5+f)*m+1,y=(-1-d)*_+(1.5+d)*g+.5*m,b=d*_-d*g;for(let S=0;S!==a;++S)r[S]=x*o[u+S]+v*o[l+S]+y*o[c+S]+b*o[h+S];return r}},ai=class extends he{static{p(this,"LinearInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=(i-e)/(s-e),h=1-u;for(let f=0;f!==a;++f)r[f]=o[l+f]*h+o[c+f]*u;return r}},ci=class extends he{static{p(this,"DiscreteInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t){return this.copySampleValue_(t-1)}},li=class extends he{static{p(this,"BezierInterpolant")}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this.inTangents,h=this.outTangents;if(!u||!h){let m=(i-e)/(s-e),g=1-m;for(let _=0;_!==a;++_)r[_]=o[l+_]*g+o[c+_]*m;return r}let f=a*2,d=t-1;for(let m=0;m!==a;++m){let g=o[l+m],_=o[c+m],x=d*f+m*2,v=h[x],y=h[x+1],b=t*f+m*2,S=u[b],A=u[b+1],M=(i-e)/(s-e),T,I,E,N,L;for(let R=0;R<8;R++){T=M*M,I=T*M,E=1-M,N=E*E,L=N*E;let P=L*e+3*N*M*v+3*E*T*S+I*s-i;if(Math.abs(P)<1e-10)break;let w=3*N*(v-e)+6*E*M*(S-v)+3*T*(s-S);if(Math.abs(w)<1e-10)break;M=M-P/w,M=Math.max(0,Math.min(1,M))}r[m]=L*g+3*N*M*y+3*E*T*A+I*_}return r}},Dt=class{static{p(this,"KeyframeTrack")}constructor(t,e,i,s){if(t===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(e===void 0||e.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+t);this.name=t,this.times=Zn(e,this.TimeBufferType),this.values=Zn(i,this.ValueBufferType),this.setInterpolation(s||this.DefaultInterpolation)}static toJSON(t){let e=t.constructor,i;if(e.toJSON!==this.toJSON)i=e.toJSON(t);else{i={name:t.name,times:Zn(t.times,Array),values:Zn(t.values,Array)};let s=t.getInterpolation();s!==t.DefaultInterpolation&&(i.interpolation=s)}return i.type=t.ValueTypeName,i}InterpolantFactoryMethodDiscrete(t){return new ci(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodLinear(t){return new ai(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodSmooth(t){return new oi(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodBezier(t){let e=new li(this.times,this.values,this.getValueSize(),t);return this.settings&&(e.inTangents=this.settings.inTangents,e.outTangents=this.settings.outTangents),e}setInterpolation(t){let e;switch(t){case xn:e=this.InterpolantFactoryMethodDiscrete;break;case jn:e=this.InterpolantFactoryMethodLinear;break;case Jn:e=this.InterpolantFactoryMethodSmooth;break;case is:e=this.InterpolantFactoryMethodBezier;break}if(e===void 0){let i="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(t!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(i);return pt("KeyframeTrack:",i),this}return this.createInterpolant=e,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return xn;case this.InterpolantFactoryMethodLinear:return jn;case this.InterpolantFactoryMethodSmooth:return Jn;case this.InterpolantFactoryMethodBezier:return is}}getValueSize(){return this.values.length/this.times.length}shift(t){if(t!==0){let e=this.times;for(let i=0,s=e.length;i!==s;++i)e[i]+=t}return this}scale(t){if(t!==1){let e=this.times;for(let i=0,s=e.length;i!==s;++i)e[i]*=t}return this}trim(t,e){let i=this.times,s=i.length,r=0,o=s-1;for(;r!==s&&i[r]<t;)++r;for(;o!==-1&&i[o]>e;)--o;if(++o,r!==0||o!==s){r>=o&&(o=Math.max(o,1),r=o-1);let a=this.getValueSize();this.times=i.slice(r,o),this.values=this.values.slice(r*a,o*a)}return this}validate(){let t=!0,e=this.getValueSize();e-Math.floor(e)!==0&&(rt("KeyframeTrack: Invalid value size in track.",this),t=!1);let i=this.times,s=this.values,r=i.length;r===0&&(rt("KeyframeTrack: Track is empty.",this),t=!1);let o=null;for(let a=0;a!==r;a++){let c=i[a];if(typeof c=="number"&&isNaN(c)){rt("KeyframeTrack: Time is not a valid number.",this,a,c),t=!1;break}if(o!==null&&o>c){rt("KeyframeTrack: Out of order keys.",this,a,c,o),t=!1;break}o=c}if(s!==void 0&&tc(s))for(let a=0,c=s.length;a!==c;++a){let l=s[a];if(isNaN(l)){rt("KeyframeTrack: Value is not a valid number.",this,a,l),t=!1;break}}return t}optimize(){let t=this.times.slice(),e=this.values.slice(),i=this.getValueSize(),s=this.getInterpolation()===Jn,r=t.length-1,o=1;for(let a=1;a<r;++a){let c=!1,l=t[a],u=t[a+1];if(l!==u&&(a!==1||l!==t[0]))if(s)c=!0;else{let h=a*i,f=h-i,d=h+i;for(let m=0;m!==i;++m){let g=e[h+m];if(g!==e[f+m]||g!==e[d+m]){c=!0;break}}}if(c){if(a!==o){t[o]=t[a];let h=a*i,f=o*i;for(let d=0;d!==i;++d)e[f+d]=e[h+d]}++o}}if(r>0){t[o]=t[r];for(let a=r*i,c=o*i,l=0;l!==i;++l)e[c+l]=e[a+l];++o}return o!==t.length?(this.times=t.slice(0,o),this.values=e.slice(0,o*i)):(this.times=t,this.values=e),this}clone(){let t=this.times.slice(),e=this.values.slice(),i=this.constructor,s=new i(this.name,t,e);return s.createInterpolant=this.createInterpolant,s}};Dt.prototype.ValueTypeName="";Dt.prototype.TimeBufferType=Float32Array;Dt.prototype.ValueBufferType=Float32Array;Dt.prototype.DefaultInterpolation=jn;var fe=class extends Dt{static{p(this,"BooleanKeyframeTrack")}constructor(t,e,i){super(t,e,i)}};fe.prototype.ValueTypeName="bool";fe.prototype.ValueBufferType=Array;fe.prototype.DefaultInterpolation=xn;fe.prototype.InterpolantFactoryMethodLinear=void 0;fe.prototype.InterpolantFactoryMethodSmooth=void 0;var ui=class extends Dt{static{p(this,"ColorKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};ui.prototype.ValueTypeName="color";var hi=class extends Dt{static{p(this,"NumberKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};hi.prototype.ValueTypeName="number";var fi=class extends he{static{p(this,"QuaternionLinearInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=(i-e)/(s-e),l=t*a;for(let u=l+a;l!==u;l+=4)qt.slerpFlat(r,0,o,l-a,o,l,c);return r}},Sn=class extends Dt{static{p(this,"QuaternionKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}InterpolantFactoryMethodLinear(t){return new fi(this.times,this.values,this.getValueSize(),t)}};Sn.prototype.ValueTypeName="quaternion";Sn.prototype.InterpolantFactoryMethodSmooth=void 0;var de=class extends Dt{static{p(this,"StringKeyframeTrack")}constructor(t,e,i){super(t,e,i)}};de.prototype.ValueTypeName="string";de.prototype.ValueBufferType=Array;de.prototype.DefaultInterpolation=xn;de.prototype.InterpolantFactoryMethodLinear=void 0;de.prototype.InterpolantFactoryMethodSmooth=void 0;var di=class extends Dt{static{p(this,"VectorKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};di.prototype.ValueTypeName="vector";var pi=class{static{p(this,"LoadingManager")}constructor(t,e,i){let s=this,r=!1,o=0,a=0,c,l=[];this.onStart=void 0,this.onLoad=t,this.onProgress=e,this.onError=i,this._abortController=null,this.itemStart=function(u){a++,r===!1&&s.onStart!==void 0&&s.onStart(u,o,a),r=!0},this.itemEnd=function(u){o++,s.onProgress!==void 0&&s.onProgress(u,o,a),o===a&&(r=!1,s.onLoad!==void 0&&s.onLoad())},this.itemError=function(u){s.onError!==void 0&&s.onError(u)},this.resolveURL=function(u){return u=u.normalize("NFC"),c?c(u):u},this.setURLModifier=function(u){return c=u,this},this.addHandler=function(u,h){return l.push(u,h),this},this.removeHandler=function(u){let h=l.indexOf(u);return h!==-1&&l.splice(h,2),this},this.getHandler=function(u){for(let h=0,f=l.length;h<f;h+=2){let d=l[h],m=l[h+1];if(d.global&&(d.lastIndex=0),d.test(u))return m}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},so=new pi,mi=class{static{p(this,"Loader")}constructor(t){this.manager=t!==void 0?t:so,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(t,e){let i=this;return new Promise(function(s,r){i.load(t,s,e,r)})}parse(){}setCrossOrigin(t){return this.crossOrigin=t,this}setWithCredentials(t){return this.withCredentials=t,this}setPath(t){return this.path=t,this}setResourcePath(t){return this.resourcePath=t,this}setRequestHeader(t){return this.requestHeader=t,this}abort(){return this}};mi.DEFAULT_MATERIAL_NAME="__DEFAULT";var Cs="\\[\\]\\.:\\/",Lc=new RegExp("["+Cs+"]","g"),Rs="[^"+Cs+"]",Dc="[^"+Cs.replace("\\.","")+"]",Uc=/((?:WC+[\/:])*)/.source.replace("WC",Rs),Fc=/(WCOD+)?/.source.replace("WCOD",Dc),Oc=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",Rs),Bc=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",Rs),zc=new RegExp("^"+Uc+Fc+Oc+Bc+"$"),kc=["material","materials","bones","map"],gs=class{static{p(this,"Composite")}constructor(t,e,i){let s=i||it.parseTrackName(e);this._targetGroup=t,this._bindings=t.subscribe_(e,s)}getValue(t,e){this.bind();let i=this._targetGroup.nCachedObjects_,s=this._bindings[i];s!==void 0&&s.getValue(t,e)}setValue(t,e){let i=this._bindings;for(let s=this._targetGroup.nCachedObjects_,r=i.length;s!==r;++s)i[s].setValue(t,e)}bind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,i=t.length;e!==i;++e)t[e].bind()}unbind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,i=t.length;e!==i;++e)t[e].unbind()}},it=class n{static{p(this,"PropertyBinding")}constructor(t,e,i){this.path=e,this.parsedPath=i||n.parseTrackName(e),this.node=n.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,e,i){return t&&t.isAnimationObjectGroup?new n.Composite(t,e,i):new n(t,e,i)}static sanitizeNodeName(t){return t.replace(/\s/g,"_").replace(Lc,"")}static parseTrackName(t){let e=zc.exec(t);if(e===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+t);let i={nodeName:e[2],objectName:e[3],objectIndex:e[4],propertyName:e[5],propertyIndex:e[6]},s=i.nodeName&&i.nodeName.lastIndexOf(".");if(s!==void 0&&s!==-1){let r=i.nodeName.substring(s+1);kc.indexOf(r)!==-1&&(i.nodeName=i.nodeName.substring(0,s),i.objectName=r)}if(i.propertyName===null||i.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+t);return i}static findNode(t,e){if(e===void 0||e===""||e==="."||e===-1||e===t.name||e===t.uuid)return t;if(t.skeleton){let i=t.skeleton.getBoneByName(e);if(i!==void 0)return i}if(t.children){let i=p(function(r){for(let o=0;o<r.length;o++){let a=r[o];if(a.name===e||a.uuid===e)return a;let c=i(a.children);if(c)return c}return null},"searchNodeSubtree"),s=i(t.children);if(s)return s}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(t,e){t[e]=this.targetObject[this.propertyName]}_getValue_array(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)t[e++]=i[s]}_getValue_arrayElement(t,e){t[e]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(t,e){this.resolvedProperty.toArray(t,e)}_setValue_direct(t,e){this.targetObject[this.propertyName]=t[e]}_setValue_direct_setNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++]}_setValue_array_setNeedsUpdate(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(t,e){this.resolvedProperty[this.propertyIndex]=t[e]}_setValue_arrayElement_setNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(t,e){this.resolvedProperty.fromArray(t,e)}_setValue_fromArray_setNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(t,e){this.bind(),this.getValue(t,e)}_setValue_unbound(t,e){this.bind(),this.setValue(t,e)}bind(){let t=this.node,e=this.parsedPath,i=e.objectName,s=e.propertyName,r=e.propertyIndex;if(t||(t=n.findNode(this.rootNode,e.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){pt("PropertyBinding: No target node found for track: "+this.path+".");return}if(i){let l=e.objectIndex;switch(i){case"materials":if(!t.material){rt("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.materials){rt("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}t=t.material.materials;break;case"bones":if(!t.skeleton){rt("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}t=t.skeleton.bones;for(let u=0;u<t.length;u++)if(t[u].name===l){l=u;break}break;case"map":if("map"in t){t=t.map;break}if(!t.material){rt("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.map){rt("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}t=t.material.map;break;default:if(t[i]===void 0){rt("PropertyBinding: Can not bind to objectName of node undefined.",this);return}t=t[i]}if(l!==void 0){if(t[l]===void 0){rt("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,t);return}t=t[l]}}let o=t[s];if(o===void 0){let l=e.nodeName;rt("PropertyBinding: Trying to update property for track: "+l+"."+s+" but it wasn't found.",t);return}let a=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?a=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(a=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(r!==void 0){if(s==="morphTargetInfluences"){if(!t.geometry){rt("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!t.geometry.morphAttributes){rt("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}t.morphTargetDictionary[r]!==void 0&&(r=t.morphTargetDictionary[r])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=r}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=s;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][a]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};it.Composite=gs;it.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};it.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};it.prototype.GetterByBindingType=[it.prototype._getValue_direct,it.prototype._getValue_array,it.prototype._getValue_arrayElement,it.prototype._getValue_toArray];it.prototype.SetterByBindingTypeAndVersioning=[[it.prototype._setValue_direct,it.prototype._setValue_direct_setNeedsUpdate,it.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[it.prototype._setValue_array,it.prototype._setValue_array_setNeedsUpdate,it.prototype._setValue_array_setMatrixWorldNeedsUpdate],[it.prototype._setValue_arrayElement,it.prototype._setValue_arrayElement_setNeedsUpdate,it.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[it.prototype._setValue_fromArray,it.prototype._setValue_fromArray_setNeedsUpdate,it.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var Vd=new Float32Array(1);var xs=class n{static{p(this,"Matrix2")}static{n.prototype.isMatrix2=!0}constructor(t,e,i,s){this.elements=[1,0,0,1],t!==void 0&&this.set(t,e,i,s)}identity(){return this.set(1,0,0,1),this}fromArray(t,e=0){for(let i=0;i<4;i++)this.elements[i]=t[i+e];return this}set(t,e,i,s){let r=this.elements;return r[0]=t,r[2]=e,r[1]=i,r[3]=s,this}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"185"}}));typeof window<"u"&&(window.__THREE__?pt("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="185");var Vc=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,Gc=`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,Hc=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,Wc=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,Xc=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,qc=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,$c=`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,Yc=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,Zc=`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,Jc=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,Kc=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,jc=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,Qc=`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,tl=`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,el=`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,nl=`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,il=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,sl=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,rl=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,ol=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,al=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,cl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,ll=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,ul=`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
#define inverseTransformDirection transformDirectionByInverseViewMatrix
vec3 transformNormalByInverseViewMatrix( in vec3 normal, in mat4 viewMatrix ) {
	return normalize( ( vec4( normal, 0.0 ) * viewMatrix ).xyz );
}
vec3 transformDirectionByInverseViewMatrix( in vec3 dir, in mat4 viewMatrix ) {
	return normalize( ( vec4( dir, 0.0 ) * viewMatrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,hl=`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,fl=`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
#endif`,dl=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,pl=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,ml=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,gl=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,xl="gl_FragColor = linearToOutputTexel( gl_FragColor );",_l=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,yl=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * reflectVec );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,vl=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,Ml=`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,bl=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,Sl=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,Al=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,Tl=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,wl=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,El=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,Cl=`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,Rl=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,Il=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,Pl=`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,Nl=`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif
#include <lightprobes_pars_fragment>`,Ll=`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
#endif`,Dl=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,Ul=`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,Fl=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,Ol=`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,Bl=`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,zl=`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0;
		vec3 iridescenceFresnelDielectric;
		vec3 iridescenceFresnelMetallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		return 0.5 / max( gv + gl, EPSILON );
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
vec3 BRDF_GGX_Multiscatter( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 singleScatter = BRDF_GGX( lightDir, viewDir, normal, material );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 dfgV = texture2D( dfgLUT, vec2( material.roughness, dotNV ) ).rg;
	vec2 dfgL = texture2D( dfgLUT, vec2( material.roughness, dotNL ) ).rg;
	vec3 FssEss_V = material.specularColorBlended * dfgV.x + material.specularF90 * dfgV.y;
	vec3 FssEss_L = material.specularColorBlended * dfgL.x + material.specularF90 * dfgL.y;
	float Ess_V = dfgV.x + dfgV.y;
	float Ess_L = dfgL.x + dfgL.y;
	float Ems_V = 1.0 - Ess_V;
	float Ems_L = 1.0 - Ess_L;
	vec3 Favg = material.specularColorBlended + ( 1.0 - material.specularColorBlended ) * 0.047619;
	vec3 Fms = FssEss_V * FssEss_L * Favg / ( 1.0 - Ems_V * Ems_L * Favg + EPSILON );
	float compensationFactor = Ems_V * Ems_L;
	vec3 multiScatter = Fms * compensationFactor;
	return singleScatter + multiScatter;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	reflectedLight.directSpecular += irradiance * BRDF_GGX_Multiscatter( directLight.direction, geometryViewDir, geometryNormal, material );
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.iridescence, material.iridescenceFresnelDielectric, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceFresnelMetallic, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,kl=`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		material.iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		material.iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( material.iridescenceFresnelDielectric, material.iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0 = Schlick_to_F0( material.iridescenceFresnel, 1.0, dotNVi );
	}
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
	#ifdef USE_LIGHT_PROBES_GRID
		vec3 probeWorldPos = ( ( vec4( geometryPosition, 1.0 ) - viewMatrix[ 3 ] ) * viewMatrix ).xyz;
		vec3 probeWorldNormal = transformNormalByInverseViewMatrix( geometryNormal, viewMatrix );
		irradiance += getLightProbeGridIrradiance( probeWorldPos, probeWorldNormal );
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,Vl=`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		radiance += getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		radiance += getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,Gl=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,Hl=`#ifdef USE_LIGHT_PROBES_GRID
uniform highp sampler3D probesSH;
uniform vec3 probesMin;
uniform vec3 probesMax;
uniform vec3 probesResolution;
vec3 getLightProbeGridIrradiance( vec3 worldPos, vec3 worldNormal ) {
	vec3 res = probesResolution;
	vec3 gridRange = probesMax - probesMin;
	vec3 resMinusOne = res - 1.0;
	vec3 probeSpacing = gridRange / resMinusOne;
	vec3 samplePos = worldPos + worldNormal * probeSpacing * 0.5;
	vec3 uvw = clamp( ( samplePos - probesMin ) / gridRange, 0.0, 1.0 );
	uvw = uvw * resMinusOne / res + 0.5 / res;
	float nz          = res.z;
	float paddedSlices = nz + 2.0;
	float atlasDepth  = 7.0 * paddedSlices;
	float uvZBase     = uvw.z * nz + 1.0;
	vec4 s0 = texture( probesSH, vec3( uvw.xy, ( uvZBase                       ) / atlasDepth ) );
	vec4 s1 = texture( probesSH, vec3( uvw.xy, ( uvZBase +       paddedSlices   ) / atlasDepth ) );
	vec4 s2 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 2.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s3 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 3.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s4 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 4.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s5 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 5.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s6 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 6.0 * paddedSlices   ) / atlasDepth ) );
	vec3 c0 = s0.xyz;
	vec3 c1 = vec3( s0.w, s1.xy );
	vec3 c2 = vec3( s1.zw, s2.x );
	vec3 c3 = s2.yzw;
	vec3 c4 = s3.xyz;
	vec3 c5 = vec3( s3.w, s4.xy );
	vec3 c6 = vec3( s4.zw, s5.x );
	vec3 c7 = s5.yzw;
	vec3 c8 = s6.xyz;
	float x = worldNormal.x, y = worldNormal.y, z = worldNormal.z;
	vec3 result = c0 * 0.886227;
	result += c1 * 2.0 * 0.511664 * y;
	result += c2 * 2.0 * 0.511664 * z;
	result += c3 * 2.0 * 0.511664 * x;
	result += c4 * 2.0 * 0.429043 * x * y;
	result += c5 * 2.0 * 0.429043 * y * z;
	result += c6 * ( 0.743125 * z * z - 0.247708 );
	result += c7 * 2.0 * 0.429043 * x * z;
	result += c8 * 0.429043 * ( x * x - y * y );
	return max( result, vec3( 0.0 ) );
}
#endif`,Wl=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,Xl=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,ql=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,$l=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,Yl=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,Zl=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,Jl=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,Kl=`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,jl=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,Ql=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,tu=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,eu=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,nu=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,iu=`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,su=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,ru=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#ifdef DOUBLE_SIDED
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#ifdef DOUBLE_SIDED
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,ou=`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#if defined( USE_PACKED_NORMALMAP )
		mapN = vec3( mapN.xy, sqrt( saturate( 1.0 - dot( mapN.xy, mapN.xy ) ) ) );
	#endif
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,au=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,cu=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,lu=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,uu=`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,hu=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,fu=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,du=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,pu=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,mu=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,gu=`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,xu=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,_u=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,yu=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,vu=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,Mu=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,bu=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,Su=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,Au=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,Tu=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,wu=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,Eu=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,Cu=`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,Ru=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,Iu=`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,Pu=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,Nu=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,Lu=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,Du=`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,Uu=`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,Fu=`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,Ou=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,Bu=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,zu=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,ku=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,Vu=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,Gu=`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Hu=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,Wu=`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vWorldDirection );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Xu=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,qu=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,$u=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,Yu=`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,Zu=`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,Ju=`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,Ku=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,ju=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Qu=`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,th=`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,eh=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,nh=`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,ih=`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,sh=`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,rh=`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,oh=`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,ah=`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,ch=`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,lh=`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,uh=`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,hh=`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,fh=`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,dh=`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,ph=`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,mh=`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,gh=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,xh=`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,_h=`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,yh=`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,vh=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,Z={alphahash_fragment:Vc,alphahash_pars_fragment:Gc,alphamap_fragment:Hc,alphamap_pars_fragment:Wc,alphatest_fragment:Xc,alphatest_pars_fragment:qc,aomap_fragment:$c,aomap_pars_fragment:Yc,batching_pars_vertex:Zc,batching_vertex:Jc,begin_vertex:Kc,beginnormal_vertex:jc,bsdfs:Qc,iridescence_fragment:tl,bumpmap_pars_fragment:el,clipping_planes_fragment:nl,clipping_planes_pars_fragment:il,clipping_planes_pars_vertex:sl,clipping_planes_vertex:rl,color_fragment:ol,color_pars_fragment:al,color_pars_vertex:cl,color_vertex:ll,common:ul,cube_uv_reflection_fragment:hl,defaultnormal_vertex:fl,displacementmap_pars_vertex:dl,displacementmap_vertex:pl,emissivemap_fragment:ml,emissivemap_pars_fragment:gl,colorspace_fragment:xl,colorspace_pars_fragment:_l,envmap_fragment:yl,envmap_common_pars_fragment:vl,envmap_pars_fragment:Ml,envmap_pars_vertex:bl,envmap_physical_pars_fragment:Ll,envmap_vertex:Sl,fog_vertex:Al,fog_pars_vertex:Tl,fog_fragment:wl,fog_pars_fragment:El,gradientmap_pars_fragment:Cl,lightmap_pars_fragment:Rl,lights_lambert_fragment:Il,lights_lambert_pars_fragment:Pl,lights_pars_begin:Nl,lights_toon_fragment:Dl,lights_toon_pars_fragment:Ul,lights_phong_fragment:Fl,lights_phong_pars_fragment:Ol,lights_physical_fragment:Bl,lights_physical_pars_fragment:zl,lights_fragment_begin:kl,lights_fragment_maps:Vl,lights_fragment_end:Gl,lightprobes_pars_fragment:Hl,logdepthbuf_fragment:Wl,logdepthbuf_pars_fragment:Xl,logdepthbuf_pars_vertex:ql,logdepthbuf_vertex:$l,map_fragment:Yl,map_pars_fragment:Zl,map_particle_fragment:Jl,map_particle_pars_fragment:Kl,metalnessmap_fragment:jl,metalnessmap_pars_fragment:Ql,morphinstance_vertex:tu,morphcolor_vertex:eu,morphnormal_vertex:nu,morphtarget_pars_vertex:iu,morphtarget_vertex:su,normal_fragment_begin:ru,normal_fragment_maps:ou,normal_pars_fragment:au,normal_pars_vertex:cu,normal_vertex:lu,normalmap_pars_fragment:uu,clearcoat_normal_fragment_begin:hu,clearcoat_normal_fragment_maps:fu,clearcoat_pars_fragment:du,iridescence_pars_fragment:pu,opaque_fragment:mu,packing:gu,premultiplied_alpha_fragment:xu,project_vertex:_u,dithering_fragment:yu,dithering_pars_fragment:vu,roughnessmap_fragment:Mu,roughnessmap_pars_fragment:bu,shadowmap_pars_fragment:Su,shadowmap_pars_vertex:Au,shadowmap_vertex:Tu,shadowmask_pars_fragment:wu,skinbase_vertex:Eu,skinning_pars_vertex:Cu,skinning_vertex:Ru,skinnormal_vertex:Iu,specularmap_fragment:Pu,specularmap_pars_fragment:Nu,tonemapping_fragment:Lu,tonemapping_pars_fragment:Du,transmission_fragment:Uu,transmission_pars_fragment:Fu,uv_pars_fragment:Ou,uv_pars_vertex:Bu,uv_vertex:zu,worldpos_vertex:ku,background_vert:Vu,background_frag:Gu,backgroundCube_vert:Hu,backgroundCube_frag:Wu,cube_vert:Xu,cube_frag:qu,depth_vert:$u,depth_frag:Yu,distance_vert:Zu,distance_frag:Ju,equirect_vert:Ku,equirect_frag:ju,linedashed_vert:Qu,linedashed_frag:th,meshbasic_vert:eh,meshbasic_frag:nh,meshlambert_vert:ih,meshlambert_frag:sh,meshmatcap_vert:rh,meshmatcap_frag:oh,meshnormal_vert:ah,meshnormal_frag:ch,meshphong_vert:lh,meshphong_frag:uh,meshphysical_vert:hh,meshphysical_frag:fh,meshtoon_vert:dh,meshtoon_frag:ph,points_vert:mh,points_frag:gh,shadow_vert:xh,shadow_frag:_h,sprite_vert:yh,sprite_frag:vh},G={common:{diffuse:{value:new xt(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Y}},envmap:{envMap:{value:null},envMapRotation:{value:new Y},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Y}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Y}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Y},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Y},normalScale:{value:new mt(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Y},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Y}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Y}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Y}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new xt(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new V},probesMax:{value:new V},probesResolution:{value:new V}},points:{diffuse:{value:new xt(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0},uvTransform:{value:new Y}},sprite:{diffuse:{value:new xt(16777215)},opacity:{value:1},center:{value:new mt(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}}},ro={basic:{uniforms:bt([G.common,G.specularmap,G.envmap,G.aomap,G.lightmap,G.fog]),vertexShader:Z.meshbasic_vert,fragmentShader:Z.meshbasic_frag},lambert:{uniforms:bt([G.common,G.specularmap,G.envmap,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.fog,G.lights,{emissive:{value:new xt(0)},envMapIntensity:{value:1}}]),vertexShader:Z.meshlambert_vert,fragmentShader:Z.meshlambert_frag},phong:{uniforms:bt([G.common,G.specularmap,G.envmap,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.fog,G.lights,{emissive:{value:new xt(0)},specular:{value:new xt(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:Z.meshphong_vert,fragmentShader:Z.meshphong_frag},standard:{uniforms:bt([G.common,G.envmap,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.roughnessmap,G.metalnessmap,G.fog,G.lights,{emissive:{value:new xt(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag},toon:{uniforms:bt([G.common,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.gradientmap,G.fog,G.lights,{emissive:{value:new xt(0)}}]),vertexShader:Z.meshtoon_vert,fragmentShader:Z.meshtoon_frag},matcap:{uniforms:bt([G.common,G.bumpmap,G.normalmap,G.displacementmap,G.fog,{matcap:{value:null}}]),vertexShader:Z.meshmatcap_vert,fragmentShader:Z.meshmatcap_frag},points:{uniforms:bt([G.points,G.fog]),vertexShader:Z.points_vert,fragmentShader:Z.points_frag},dashed:{uniforms:bt([G.common,G.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Z.linedashed_vert,fragmentShader:Z.linedashed_frag},depth:{uniforms:bt([G.common,G.displacementmap]),vertexShader:Z.depth_vert,fragmentShader:Z.depth_frag},normal:{uniforms:bt([G.common,G.bumpmap,G.normalmap,G.displacementmap,{opacity:{value:1}}]),vertexShader:Z.meshnormal_vert,fragmentShader:Z.meshnormal_frag},sprite:{uniforms:bt([G.sprite,G.fog]),vertexShader:Z.sprite_vert,fragmentShader:Z.sprite_frag},background:{uniforms:{uvTransform:{value:new Y},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Z.background_vert,fragmentShader:Z.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Y}},vertexShader:Z.backgroundCube_vert,fragmentShader:Z.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Z.cube_vert,fragmentShader:Z.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Z.equirect_vert,fragmentShader:Z.equirect_frag},distance:{uniforms:bt([G.common,G.displacementmap,{referencePosition:{value:new V},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Z.distance_vert,fragmentShader:Z.distance_frag},shadow:{uniforms:bt([G.lights,G.fog,{color:{value:new xt(0)},opacity:{value:1}}]),vertexShader:Z.shadow_vert,fragmentShader:Z.shadow_frag}};ro.physical={uniforms:bt([ro.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Y},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Y},clearcoatNormalScale:{value:new mt(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Y},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Y},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Y},sheen:{value:0},sheenColor:{value:new xt(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Y},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Y},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Y},transmissionSamplerSize:{value:new mt},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Y},attenuationDistance:{value:0},attenuationColor:{value:new xt(0)},specularColor:{value:new xt(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Y},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Y},anisotropyVector:{value:new mt},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Y}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag};var Mh=new Y;Mh.set(-1,0,0,0,1,0,0,0,1);var dy={[_s]:"LINEAR_TONE_MAPPING",[ys]:"REINHARD_TONE_MAPPING",[vs]:"CINEON_TONE_MAPPING",[Ms]:"ACES_FILMIC_TONE_MAPPING",[Ss]:"AGX_TONE_MAPPING",[As]:"NEUTRAL_TONE_MAPPING",[bs]:"CUSTOM_TONE_MAPPING"};var py=new Float32Array(16),my=new Float32Array(9),gy=new Float32Array(4);var xy={[_s]:"Linear",[ys]:"Reinhard",[vs]:"Cineon",[Ms]:"ACESFilmic",[Ss]:"AgX",[As]:"Neutral",[bs]:"Custom"};var _y={[zr]:"SHADOWMAP_TYPE_PCF",[kr]:"SHADOWMAP_TYPE_VSM"};var yy={[Wr]:"ENVMAP_TYPE_CUBE",[ws]:"ENVMAP_TYPE_CUBE",[Xr]:"ENVMAP_TYPE_CUBE_UV"};var vy={[ws]:"ENVMAP_MODE_REFRACTION"};var My={[Vr]:"ENVMAP_BLENDING_MULTIPLY",[Gr]:"ENVMAP_BLENDING_MIX",[Hr]:"ENVMAP_BLENDING_ADD"};var bh=new Y;bh.set(-1,0,0,0,1,0,0,0,1);var by=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]);function Is(n,t,e,i){let s=e;if(i>=n[s])return s-1;if(i<=n[t])return t;let r=t,o=s,a=r+o>>1;for(;i<n[a]||i>=n[a+1];)i<n[a]?o=a:r=a,a=r+o>>1;return a}p(Is,"findSpan");var oo=new Map;function An(n,t){let e=oo.get(t);e||oo.set(t,e=[]);let i=e[n];return i||(e[n]=i=new Float64Array(t)),i}p(An,"scratch");function Ps(n,t,e,i,s){let r=An(0,t+1),o=An(1,t+1);s[0]=1;for(let a=1;a<=t;a+=1){r[a]=i-n[e+1-a],o[a]=n[e+a]-i;let c=0;for(let l=0;l<a;l+=1){let u=s[l]/(o[l+1]+r[a-l]);s[l]=c+o[l+1]*u,c=r[a-l]*u}s[a]=c}return s}p(Ps,"basisFunctions");function ao(n,t,e,i){let s=n.deg,r=se(t,n.poles),o=se(t,n.knots),a=n.weights?se(t,n.weights):null;if(n.period){let[f,d]=n.range;(e>d||e<f)&&(e=f+((e-f)%n.period+n.period)%n.period)}let c=Is(o,s,n.n,e),l=Ps(o,s,c,e,An(2,s+1)),u=[0,0,0],h=0;for(let f=0;f<=s;f+=1){let d=c-s+f,m=a?a[d]:1,g=l[f]*m;for(let _=0;_<i;_+=1)u[_]+=g*r[d*i+_];h+=g}for(let f=0;f<i;f+=1)u[f]/=h;return u.slice(0,i)}p(ao,"evaluateBSplineCurve");var Sh={line(n,t){let{origin:e,dir:i}=n;return[e[0]+t*i[0],e[1]+t*i[1],e[2]+t*i[2]]},circle(n,t){let e=Math.cos(t)*n.radius,i=Math.sin(t)*n.radius;return Ae(n,e,i,0)},ellipse(n,t){let e=Math.cos(t)*n.majorRadius,i=Math.sin(t)*n.minorRadius;return Ae(n,e,i,0)}};function $t(n,t,e){let i=Sh[n.kind];if(i)return i(n,e);if(n.kind==="bspline")return ao(n,t,e,3);throw new Error(`unknown curve kind ${n.kind}`)}p($t,"evaluateCurve3");function Tn(n,t,e){return ao(n,t,e,2)}p(Tn,"evaluatePCurve");function Ae(n,t,e,i){let{origin:s,xdir:r,ydir:o,zdir:a}=n;return[s[0]+t*r[0]+e*o[0]+i*a[0],s[1]+t*r[1]+e*o[1]+i*a[1],s[2]+t*r[2]+e*o[2]+i*a[2]]}p(Ae,"frameMix");function Ah(n,t,e,i){let{degU:s,degV:r,nu:o,nv:a}=n,c=se(t,n.poles),l=se(t,n.knotsU),u=se(t,n.knotsV),h=n.weights?se(t,n.weights):null,f=Is(l,s,o,e),d=Is(u,r,a,i),m=Ps(l,s,f,e,An(2,s+1)),g=Ps(u,r,d,i,An(3,r+1)),_=0,x=0,v=0,y=0;for(let b=0;b<=s;b+=1){let S=f-s+b;for(let A=0;A<=r;A+=1){let M=d-r+A,T=S*a+M,I=h?h[T]:1,E=m[b]*g[A]*I;_+=E*c[T*3],x+=E*c[T*3+1],v+=E*c[T*3+2],y+=E}}return[_/y,x/y,v/y]}p(Ah,"evaluateNurbsSurface");var Th={plane(n,t,e){return Ae(n,t,e,0)},cylinder(n,t,e){let i=n.radius;return Ae(n,i*Math.cos(t),i*Math.sin(t),e)},cone(n,t,e){let i=n.radius+e*Math.sin(n.semiAngle);return Math.abs(i)<(Math.abs(n.radius)+Math.abs(e))*Number.EPSILON*4&&(i=0),Ae(n,i*Math.cos(t),i*Math.sin(t),e*Math.cos(n.semiAngle))},sphere(n,t,e){let i=n.radius,s=Math.abs(Math.cos(e))<Number.EPSILON*4?0:Math.cos(e);return Ae(n,i*s*Math.cos(t),i*s*Math.sin(t),i*Math.sin(e))},torus(n,t,e){let i=n.majorRadius+n.minorRadius*Math.cos(e);return Ae(n,i*Math.cos(t),i*Math.sin(t),n.minorRadius*Math.sin(e))}};function ct(n,t,e,i){let s=Th[n.kind];if(s)return s(n,e,i);if(n.kind==="nurbs")return Ah(n,t,e,i);if(n.kind==="revolution"){let r=$t(n.profile,t,i);return wh(r,n.origin,n.dir,e)}if(n.kind==="extrusion"){let r=$t(n.profile,t,e);return[r[0]+i*n.dir[0],r[1]+i*n.dir[1],r[2]+i*n.dir[2]]}throw new Error(`unknown surface kind ${n.kind}`)}p(ct,"evaluateSurface");function wh(n,t,e,i){let s=n[0]-t[0],r=n[1]-t[1],o=n[2]-t[2],[a,c,l]=e,u=Math.cos(i),h=Math.sin(i),f=a*s+c*r+l*o,d=c*o-l*r,m=l*s-a*o,g=a*r-c*s;return[t[0]+s*u+d*h+a*f*(1-u),t[1]+r*u+m*h+c*f*(1-u),t[2]+o*u+g*h+l*f*(1-u)]}p(wh,"rotateAroundAxis");function wn(n,t,e,i,s,r){if(["plane","cylinder","cone","sphere","torus"].includes(n.kind)){let{xdir:M,ydir:T,zdir:I}=n,E=[M[1]*T[2]-M[2]*T[1],M[2]*T[0]-M[0]*T[2],M[0]*T[1]-M[1]*T[0]],N=E[0]*I[0]+E[1]*I[1]+E[2]*I[2]<0?-1:1,L=0,R=0,C=1;if(n.kind!=="plane"){let w=n.kind==="cone"?-n.semiAngle:n.kind==="cylinder"?0:i;L=Math.cos(e)*Math.cos(w),R=Math.sin(e)*Math.cos(w),C=Math.sin(w)}let P=(r?-1:1)*N;return[0,1,2].map(w=>P*(L*M[w]+R*T[w]+C*I[w]))}let[o,a,c,l]=s,u=Math.max((a-o)*1e-4,1e-7),h=Math.max((l-c)*1e-4,1e-7),f=ct(n,t,e-u,i),d=ct(n,t,e+u,i),m=ct(n,t,e,i-h),g=ct(n,t,e,i+h),_=[d[0]-f[0],d[1]-f[1],d[2]-f[2]],x=[g[0]-m[0],g[1]-m[1],g[2]-m[2]],v=_[1]*x[2]-_[2]*x[1],y=_[2]*x[0]-_[0]*x[2],b=_[0]*x[1]-_[1]*x[0],S=Math.hypot(v,y,b)||1,A=r?-1:1;return v=v/S*A,y=y/S*A,b=b/S*A,[v,y,b]}p(wn,"evaluateSurfaceNormal");var pe=2,wt={chordTolerance:.0015,loopTolerance:5e-4,angleTolerance:.35,maxRefineDepth:7,minLoopSegments:8};function tt(n,t){return[n[0]-t[0],n[1]-t[1],n[2]-t[2]]}p(tt,"sub");function et(n){return Math.hypot(n[0],n[1],n[2])}p(et,"length3");function En(n,t){return n.kind==="sphere"?Math.abs(Math.cos(t))<1e-12:n.kind==="cone"?Math.abs(n.radius+t*Math.sin(n.semiAngle))<(Math.abs(n.radius)+Math.abs(t))*1e-12:!1}p(En,"singularU");function co(n,t,e,i,s){let r=[],o=[],a=[],c=[];for(let l=0;n.surface.kind!=="plane"&&l<2;l+=1){let u=n.uv[l*2],h=n.uv[l*2+1];c.push({d:l,lo:u,hi:h,epsilon:Math.max(Math.abs(u),Math.abs(h),h-u,1e-12)*2**-23})}for(let l of t){let u=!l.reversed,h=l.edgeOrd?s?.get(l.edgeOrd):null,f=null,d=null;if(h&&h.points.length>=2){let m=Ch(n,l,e,i,h);m&&(f=m.uvs,d=m.fractions)}f||(f=Eh(n,l,e,i));for(let m of f)for(let{d:g,lo:_,hi:x,epsilon:v}of c)Math.abs(m[g]-_)<=v?m[g]=_:Math.abs(m[g]-x)<=v&&(m[g]=x);u||(f.reverse(),d?.reverse());for(let m=0;m<f.length-1;m+=1)r.push(f[m]),o.push(l.edgeOrd||0),a.push(d?{ord:l.edgeOrd,f0:d[m],f1:d[m+1]}:null)}return r.segmentOrds=o,r.segmentMeta=a,r}p(co,"sampleLoopPolygon");function ho(n,t,e,i){let[s,r]=t.range,o=n.surface,a=p(g=>Tn(t,e,g),"uvOf"),c=p(g=>ct(o,e,g[0],g[1]),"xyzOf"),l=c(a(s)),u=c(a(r)),h=et(tt(l,u))<=i,f=Math.max(h?wt.minLoopSegments:2,t.n??2),d=[];for(let g=0;g<=f;g+=1)d.push(s+(r-s)*g/f);let m=0;for(;m<wt.maxRefineDepth;){let g=!1,_=[d[0]];for(let x=0;x+1<d.length;x+=1){let v=d[x],y=d[x+1],b=(v+y)/2,S=c(a(v)),A=c(a(y)),M=c(a(b)),T=[(S[0]+A[0])/2,(S[1]+A[1])/2,(S[2]+A[2])/2];et(tt(M,T))>i&&(_.push(b),g=!0),_.push(y)}if(d.length=0,d.push(..._),!g)break;m+=1}return{params:d,uvs:d.map(a)}}p(ho,"samplePCurveParams");function Eh(n,t,e,i){return ho(n,t,e,i).uvs}p(Eh,"samplePCurveAdaptive");function Ch(n,t,e,i,s){let r=ho(n,t,e,i);if(r.uvs.length<2)return null;let o=n.surface,a=r.uvs.map(S=>ct(o,e,S[0],S[1])),c=[0];for(let S=1;S<a.length;S+=1)c.push(c[S-1]+et(tt(a[S],a[S-1])));let l=c[c.length-1];if(!(l>0))return null;for(let S=0;S<c.length;S+=1)c[S]/=l;let u=s.points[0],h=s.points[s.points.length-1],f=et(tt(u,a[0]))+et(tt(h,a[a.length-1])),m=et(tt(u,a[a.length-1]))+et(tt(h,a[0]))<f,g=[],_=[],x=[],v=s.boundarySubset||s.points.map((S,A)=>A),y=v.length,b=0;for(let S=0;S<y;S+=1){let A=v[m?y-1-S:S],M=s.fractions[A],T=m?1-M:M;for(;b+1<c.length-1&&c[b+1]<T;)b+=1;let I;if(S===0)I=r.params[0];else if(S===y-1)I=r.params[r.params.length-1];else{let R=c[b],C=c[b+1],P=C>R?(T-R)/(C-R):0;I=r.params[b]+P*(r.params[b+1]-r.params[b])}let E=Tn(t,e,I),N=s.points[A],L=ct(o,e,E[0],E[1]);if(et(tt(L,N))>i*2)return null;g.push(E),_.push(M),x.push(I)}if(o.kind!=="plane"){let S=g.map(A=>ct(o,e,A[0],A[1]));for(let A=0;A<4;A+=1){let M=!1,T=[g[0]],I=[_[0]],E=[x[0]],N=[S[0]];for(let L=0;L+1<g.length;L+=1){let R=S[L],C=S[L+1],P=(x[L]+x[L+1])/2,w=Tn(t,e,P),U=ct(o,e,w[0],w[1]),F=[(R[0]+C[0])/2,(R[1]+C[1])/2,(R[2]+C[2])/2];et(tt(U,F))>i&&(T.push(w),I.push((_[L]+_[L+1])/2),E.push(P),N.push(U),M=!0),T.push(g[L+1]),I.push(_[L+1]),E.push(x[L+1]),N.push(S[L+1])}if(g.length=0,_.length=0,x.length=0,S.length=0,g.push(...T),_.push(...I),x.push(...E),S.push(...N),!M)break}}return{uvs:g,fractions:_}}p(Ch,"mapSharedEdgeToPCurve");function xi(n,t,e){let i=n.fractions,s=i.length-1;if(t<=i[0])return n.points[0];if(t>=i[s])return n.points[s];let r=0,o=s;for(;r+1<o;){let f=r+o>>1;i[f]<=t?r=f:o=f}let a=i[r],c=i[r+1];if(t===a)return n.points[r];if(t===c)return n.points[r+1];let l=c>a?(t-a)/(c-a):0;if(n.curve&&e){let f=n.params[r]+l*(n.params[r+1]-n.params[r]);return $t(n.curve,e,f)}let u=n.points[r],h=n.points[r+1];return[u[0]+l*(h[0]-u[0]),u[1]+l*(h[1]-u[1]),u[2]+l*(h[2]-u[2])]}p(xi,"edgePointAt");function Rh(n,t,e){let[i,s]=n.range,r=$t(n,t,i),o=$t(n,t,s),a=!1;if(n.kind!=="line"){let g=et(tt(r,o));for(let _ of[.25,.5,.75])g=Math.max(g,et(tt(r,$t(n,t,i+_*(s-i)))));a=et(tt(r,o))<=g*2**-21}let c=n.kind==="line"?1:Math.max(a?8:4,n.n??2),l=[];for(let g=0;g<=c;g+=1)l.push(i+(s-i)*g/c);let u=0;for(;u<wt.maxRefineDepth;){let g=!1,_=[l[0]];for(let x=0;x+1<l.length;x+=1){let v=l[x],y=l[x+1],b=(v+y)/2,S=$t(n,t,v),A=$t(n,t,y),M=$t(n,t,b),T=[(S[0]+A[0])/2,(S[1]+A[1])/2,(S[2]+A[2])/2];et(tt(M,T))>e&&(_.push(b),g=!0),_.push(y)}if(l.length=0,l.push(..._),!g)break;u+=1}let h=l.map(g=>$t(n,t,g));a&&h.length>1&&(h[h.length-1]=h[0]);let f=[0];for(let g=1;g<h.length;g+=1)f.push(f[g-1]+et(tt(h[g],h[g-1])));let d=f[f.length-1];if(d>0){for(let g=0;g<f.length;g+=1)f[g]/=d;f[f.length-1]=1}let m=[0];{let g=e*(wt.loopTolerance/wt.chordTolerance),_=0;for(let x=1;x<h.length;x+=1){if(x===h.length-1){m.push(x);break}let v=h[_],y=h[x+1],b=0;for(let S=_+1;S<=x;S+=1){let A=tt(h[S],v),M=tt(y,v),T=M[0]*M[0]+M[1]*M[1]+M[2]*M[2],I=T>0?(A[0]*M[0]+A[1]*M[1]+A[2]*M[2])/T:0,E=Math.max(0,Math.min(1,I)),N=[v[0]+E*M[0],v[1]+E*M[1],v[2]+E*M[2]];if(b=Math.max(b,et(tt(h[S],N))),b>g)break}b>g&&(m.push(x),_=x)}}return{curve:n,params:l,points:h,fractions:f,closed:a,length:d,boundarySubset:m}}p(Rh,"sampleSharedEdge");function Ih(n){let t=0;for(let e=0;e<n.length;e+=1){let[i,s]=n[e],[r,o]=n[(e+1)%n.length];t+=i*o-r*s}return t/2}p(Ih,"polygonArea");function lo(n,t,e,i,s){let[r,o,a,c]=e,l=s===0?o-r:c-a;if(l<=0)return 1;let u=4,h=0;for(let d=0;d<=u;d+=1){let m=s===0?a+(c-a)*d/u:r+(o-r)*d/u;for(let g=0;g<u;g+=1){let _=(s===0?r:a)+l*g/u,x=_+l/u,v=(_+x)/2,y=p(T=>s===0?ct(n.surface,t,T,m):ct(n.surface,t,m,T),"at"),b=y(_),S=y(x),A=y(v),M=[(b[0]+S[0])/2,(b[1]+S[1])/2,(b[2]+S[2])/2];h=Math.max(h,et(tt(A,M)))}}if(h<=i)return 1;let f=Math.sqrt(h/i);return Math.min(256,Math.max(1,Math.ceil(u*f)))}p(lo,"gridStepsForDirection");function Ph(n,t,e){let i=!1;for(let s of n)for(let r=0;r<s.length;r+=1){let[o,a]=s[r],[c,l]=s[(r+1)%s.length];a>e!=l>e&&t<(c-o)*(e-a)/(l-a)+o&&(i=!i)}return i}p(Ph,"pointInLoopsEvenOdd");function Nh(n,t,e,i,s){let r=n;for(let[o,a,c]of[[0,t,!1],[0,e,!0],[1,i,!1],[1,s,!0]]){let l=r;r=[];for(let u=0;u<l.length;u+=1){let h=l[u],f=l[(u+l.length-1)%l.length],d=c?h[o]<=a:h[o]>=a,m=c?f[o]<=a:f[o]>=a;if(d!==m){let g=(a-f[o])/(h[o]-f[o]);r.push([f[0]+g*(h[0]-f[0]),f[1]+g*(h[1]-f[1])])}d&&r.push(h)}if(r.length<3)return[]}return r}p(Nh,"clipPolygonToCell");function fo(n,t,e,i,s=1/0){let r=1/0,o=-1/0,a=1/0,c=-1/0;for(let N of e)for(let[L,R]of N)L<r&&(r=L),L>o&&(o=L),R<a&&(a=R),R>c&&(c=R);if(!(o>r)||!(c>a))return null;let l=[r,o,a,c],u=Math.min(256,Math.max(lo(n,t,l,i,0),Math.ceil((o-r)/s))),h=Math.min(256,Math.max(lo(n,t,l,i,1),n.surface.kind==="sphere"?Math.ceil((c-a)/s):1)),f=(o-r)/u,d=(c-a)/h,m=p((N,L)=>[Math.min(u-1,Math.max(0,Math.floor((N-r)/f))),Math.min(h-1,Math.max(0,Math.floor((L-a)/d)))],"cellOf"),g=new Set,_=[],x=new Map;for(let N of e){let L=N.segmentOrds||[],R=N.segmentMeta||[];for(let C=0;C<N.length;C+=1){let[P,w]=N[C],[U,F]=N[(C+1)%N.length],D=_.length;_.push([P,w,U,F,L[C]||0,R[C]||null]);let[O,k]=m(Math.min(P,U),Math.min(w,F)),[z,H]=m(Math.max(P,U),Math.max(w,F));for(let X=O;X<=z;X+=1)for(let B=k;B<=H;B+=1){let W=X*h+B;g.add(W);let q=x.get(W);q||x.set(W,q=[]),q.push(D)}}}let v=[],y=new Map,b=Math.max(Math.abs(r),Math.abs(o),o-r,1e-12)*2**-23,S=Math.max(Math.abs(a),Math.abs(c),c-a,1e-12)*2**-23,A=p((N,L)=>{let R=Math.round((N-r)/f),C=Math.round((L-a)/d),P=R===u?o:r+R*f,w=C===h?c:a+C*d;n.surface.kind!=="plane"&&(Math.abs(N-P)<=b&&(N=P),Math.abs(L-w)<=S&&(L=w));let U=`${N}:${L}`,F=y.get(U);return F===void 0&&(F=v.length,v.push([N,L]),y.set(U,F)),F},"vertexId"),M=[],T=Math.abs((o-r)*(c-a))*1e-12||1e-30,I=[],E=[];for(let N=0;N<=u;N+=1)I.push(N===u?o:r+N*f);for(let N=0;N<=h;N+=1)E.push(N===h?c:a+N*d);for(let N=0;N<u;N+=1)for(let L=0;L<h;L+=1){let R=I[N],C=I[N+1],P=E[L],w=E[L+1];if(!g.has(N*h+L)){if(!Ph(e,(R+C)/2,(P+w)/2))continue;let B=A(R,P),W=A(C,P),q=A(C,w),$=A(R,w);M.push(B,W,q,B,q,$);continue}let U=e.map(B=>Nh(B,R,C,P,w)).filter(B=>B.length>=3);if(!U.length)continue;let F=0,D=0;for(let B=0;B<U.length;B+=1){let W=Math.abs(Ih(U[B]));W>D&&(D=W,F=B)}if(D<=T)continue;let O=U[F].map(([B,W])=>new mt(B,W)),k=U.filter((B,W)=>W!==F).map(B=>B.map(([W,q])=>new mt(W,q))),z;try{z=bn.triangulateShape(O,k)}catch{continue}let H=[...O,...k.flat()],X=H.map(({x:B,y:W})=>A(B,W));for(let[B,W,q]of z){let $=H[B],J=H[W],K=H[q],Q=(J.x-$.x)*(K.y-$.y)-(K.x-$.x)*(J.y-$.y);Math.abs(Q)/2>T&&X[B]!==X[W]&&X[W]!==X[q]&&X[q]!==X[B]&&M.push(X[B],X[W],X[q])}}return{uvVerts:v,triangles:M,vertexIds:y,segmentIndex:{segments:_,segmentsByCell:x,cellOf:m,stepsV:h}}}p(fo,"gridTriangulate");function Lh(n,t,e,i,s,r){let o=s-e,a=r-i,c=o*o+a*a,l=c>0?((n-e)*o+(t-i)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=i+l*a;return{distSq:(n-u)*(n-u)+(t-h)*(t-h),t:l}}p(Lh,"projectToSegment");function uo(n,t,e,i,s,r){let o=s-e,a=r-i,c=o*o+a*a,l=c>0?((n-e)*o+(t-i)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=i+l*a;return(n-u)*(n-u)+(t-h)*(t-h)}p(uo,"pointToSegmentDistanceSq");function Dh(n,t,e,i){let s=new Map,r=p((m,g)=>m<g?m*4294967296+g:g*4294967296+m,"keyOf");for(let m=0;m<n.length;m+=3){let[g,_,x]=[n[m],n[m+1],n[m+2]];for(let[v,y]of[[g,_],[_,x],[x,g]]){let b=r(v,y);s.set(b,(s.get(b)||0)+1)}}let{segments:o,segmentsByCell:a,cellOf:c,stepsV:l}=e,u=i*i,h=new Map,f=p((m,g)=>{let _=r(m,g);if(s.get(_)!==1)return 0;let x=h.get(_);if(x!==void 0)return x;x=0;let[v,y]=t[m],[b,S]=t[g],[A,M]=c((v+b)/2,(y+S)/2),T=a.get(A*l+M)||[];for(let I of T){let[E,N,L,R,C]=o[I];if(C&&uo(v,y,E,N,L,R)<u&&uo(b,S,E,N,L,R)<u){x=C;break}}return h.set(_,x),x},"ordOfMeshEdge"),d=new Uint32Array(n.length);for(let m=0;m<n.length;m+=3){let[g,_,x]=[n[m],n[m+1],n[m+2]];d[m]=f(_,x),d[m+1]=f(x,g),d[m+2]=f(g,_)}return d}p(Dh,"attributeBoundaryEdges");function Uh(n,t,e,i={},s=null){let{chordTolerance:r,loopTolerance:o,angleTolerance:a,maxRefineDepth:c}={...wt,...i},l=o*e,u=n.loops.map(R=>co(n,R,t,l,s)).filter(R=>R.length>=3);if(!u.length)return null;let h=0;{let R=1/0,C=-1/0,P=1/0,w=-1/0;for(let F of u)for(let[D,O]of F)D<R&&(R=D),D>C&&(C=D),O<P&&(P=O),O>w&&(w=O);let U=[[R,P],[C,P],[R,w],[C,w],[(R+C)/2,(P+w)/2]].map(([F,D])=>ct(n.surface,t,F,D));for(let F=0;F<U.length;F+=1)for(let D=F+1;D<U.length;D+=1)h=Math.max(h,et(tt(U[F],U[D])))}let f=Math.max(Math.min(e,h*4),1e-9),d=r*f,m=o*f,g=m<l?n.loops.map(R=>co(n,R,t,m,s)).filter(R=>R.length>=3):u;if(!g.length)return null;let _=g.length===1&&(En(n.surface,n.uv[2])||En(n.surface,n.uv[3]))&&g[0].every(([R,C])=>R===n.uv[0]||R===n.uv[1]||C===n.uv[2]||C===n.uv[3]),x=fo(n,t,g,_?d/3:d,_?a/Math.SQRT2:1/0);if(!x)return null;let{uvVerts:v,triangles:y,vertexIds:b,segmentIndex:S}=x,A=y;if(!A.length)return null;let M=v.map(([R,C])=>ct(n.surface,t,R,C));if(_){let R=new Map,C=new Map;for(let w=0;w<v.length;w+=1){if(!En(n.surface,v[w][1]))continue;let U=v[w][1];R.has(U)?C.set(w,R.get(U)):R.set(U,w)}let P=[];for(let w=0;w<A.length;w+=3){let[U,F,D]=A.slice(w,w+3).map(O=>C.get(O)??O);et(tt(M[U],M[F]))<=e*1e-12||et(tt(M[F],M[D]))<=e*1e-12||et(tt(M[D],M[U]))<=e*1e-12||P.push(U,F,D)}A=P}let T=p(([R,C])=>wn(n.surface,t,R,C,n.uv,!1),"vertexNormal"),I=v.map(T),E=Math.cos(a),N=p((R,C)=>R<C?`${R}_${C}`:`${C}_${R}`,"edgeKey");for(let R=0;R<(_?0:c);R+=1){let C=new Set,P=new Map,w=p((O,k)=>{let z=N(O,k),H=P.get(z);if(H===void 0){let X=(v[O][0]+v[k][0])/2,B=(v[O][1]+v[k][1])/2,W=ct(n.surface,t,X,B),q=[(M[O][0]+M[k][0])/2,(M[O][1]+M[k][1])/2,(M[O][2]+M[k][2])/2];H=et(tt(W,q))>d||I[O][0]*I[k][0]+I[O][1]*I[k][1]+I[O][2]*I[k][2]<E,P.set(z,H)}return H},"edgeChordBad");for(let O=0;O<A.length;O+=3){let k=A[O],z=A[O+1],H=A[O+2],X=!1;for(let[Rt,ft]of[[k,z],[z,H],[H,k]])w(Rt,ft)&&(C.add(N(Rt,ft)),X=!0);if(X)continue;let B=(v[k][0]+v[z][0]+v[H][0])/3,W=(v[k][1]+v[z][1]+v[H][1])/3,q=ct(n.surface,t,B,W),$=[(M[k][0]+M[z][0]+M[H][0])/3,(M[k][1]+M[z][1]+M[H][1])/3,(M[k][2]+M[z][2]+M[H][2])/3],J=tt(M[z],M[k]),K=tt(M[H],M[k]),Q=[J[1]*K[2]-J[2]*K[1],J[2]*K[0]-J[0]*K[2],J[0]*K[1]-J[1]*K[0]],nt=et(Q),yt=I[k];if(nt>1e-30&&Math.abs((Q[0]*yt[0]+Q[1]*yt[1]+Q[2]*yt[2])/nt)<E||et(tt(q,$))>d){let Rt=[k,z],ft=-1;for(let[ie,At]of[[k,z],[z,H],[H,k]]){let _e=v[ie][0]-v[At][0],Ht=v[ie][1]-v[At][1],It=_e*_e+Ht*Ht;It>ft&&(ft=It,Rt=[ie,At])}C.add(N(Rt[0],Rt[1]))}}if(!C.size)break;let U=new Map,F=p((O,k)=>{let z=N(O,k);if(!C.has(z))return-1;let H=U.get(z);if(H===void 0){let X=(v[O][0]+v[k][0])/2,B=(v[O][1]+v[k][1])/2;H=v.length,v.push([X,B]),M.push(ct(n.surface,t,X,B)),I.push(T([X,B])),U.set(z,H)}return H},"midpointOf"),D=[];for(let O=0;O<A.length;O+=3){let k=A[O],z=A[O+1],H=A[O+2],X=F(k,z),B=F(z,H),W=F(H,k),q=(X>=0)+(B>=0)+(W>=0);if(q===0){D.push(k,z,H);continue}if(q===3)D.push(k,X,W,X,z,B,W,B,H,X,B,W);else if(q===2){let[$,J,K,Q,nt]=X>=0&&B>=0?[k,z,H,X,B]:B>=0&&W>=0?[z,H,k,B,W]:[H,k,z,W,X];D.push($,Q,nt,$,nt,K,Q,J,nt)}else{let[$,J,K,Q]=X>=0?[k,z,H,X]:B>=0?[z,H,k,B]:[H,k,z,W];D.push($,Q,K,Q,J,K)}}A=D}let L=new Map;if(s){let R=0,C=0;for(let[O,k]of v)R=Math.max(R,Math.abs(O)),C=Math.max(C,Math.abs(k));let P=Math.max(R,C,1)*1e-7,{segments:w,segmentsByCell:U,cellOf:F,stepsV:D}=S;for(let O=0;O<v.length;O+=1){let[k,z]=v[O],[H,X]=F(k,z),B=U.get(H*D+X);if(!B)continue;let W=new Map;for(let J of B){let[K,Q,nt,yt,Jt,Rt]=w[J];if(!Rt)continue;let ft=Lh(k,z,K,Q,nt,yt);if(ft.distSq>=P*P){let _e=P*P*16,Ht=(k-K)*(k-K)+(z-Q)*(z-Q),It=(k-nt)*(k-nt)+(z-yt)*(z-yt);if(Ht<_e)ft={distSq:Ht,t:0};else if(It<_e)ft={distSq:It,t:1};else continue}let ie=W.get(Jt);if(ie&&ie.distSq<=ft.distSq)continue;let At=ft.t<1e-9?0:ft.t>1-1e-9?1:ft.t;W.set(Jt,{distSq:ft.distSq,f:Rt.f0+At*(Rt.f1-Rt.f0)})}if(!W.size)continue;let q=[],$=null;for(let[J,{distSq:K,f:Q}]of W){let nt=s.get(J);if(!nt)continue;let yt=nt.closed&&Q>=1-1e-12?0:Q;q.push({ord:J,f:yt}),(!$||K<$.distSq)&&($={distSq:K,ord:J,f:yt,shared:nt})}q.length&&(q.sort((J,K)=>J.ord===$.ord&&J.f===$.f?-1:K.ord===$.ord&&K.f===$.f?1:0),L.set(O,q),M[O]=xi($.shared,$.f,t))}}return{uvVerts:v,xyz:M,nrm:I,triangles:A,segmentIndex:S,boundary:L,loops:g,singularGrid:_}}p(Uh,"tessellateFaceRaw");function Fh(n,t,e,i={}){if(t.singularGrid)return;let{chordTolerance:s,angleTolerance:r,maxRefineDepth:o}={...wt,...i},{uvVerts:a,xyz:c,nrm:l,boundary:u}=t,h=t.mintedVerts;if(!h?.size)return;let f=t.triangles,d=0;for(let y of c)d=Math.max(d,et(tt(y,c[0])));let m=s*Math.max(d,1e-9),g=p(([y,b])=>wn(n.surface,e,y,b,n.uv,!1),"vertexNormal"),_=Math.cos(r),x=p((y,b)=>y<b?`${y}_${b}`:`${b}_${y}`,"edgeKey"),v=Math.min(3,o);for(let y=0;y<v;y+=1){let b=new Set;for(let T=0;T<f.length;T+=3){let[I,E,N]=[f[T],f[T+1],f[T+2]];if(!(!h.has(I)&&!h.has(E)&&!h.has(N)))for(let[L,R]of[[I,E],[E,N],[N,I]]){if(u.has(L)&&u.has(R))continue;let C=(a[L][0]+a[R][0])/2,P=(a[L][1]+a[R][1])/2,w=ct(n.surface,e,C,P);if(!w||!Number.isFinite(w[0]))continue;let U=[(c[L][0]+c[R][0])/2,(c[L][1]+c[R][1])/2,(c[L][2]+c[R][2])/2];et(tt(w,U))>m&&b.add(x(L,R))}}if(!b.size)break;let S=new Map,A=p((T,I)=>{let E=x(T,I);if(!b.has(E))return-1;let N=S.get(E);if(N===void 0){let L=(a[T][0]+a[I][0])/2,R=(a[T][1]+a[I][1])/2;N=a.length,a.push([L,R]),c.push(ct(n.surface,e,L,R)),l.push(g([L,R])),S.set(E,N)}return N},"midpointOf"),M=[];for(let T=0;T<f.length;T+=3){let I=f[T],E=f[T+1],N=f[T+2],L=A(I,E),R=A(E,N),C=A(N,I),P=(L>=0)+(R>=0)+(C>=0);if(P===0)M.push(I,E,N);else if(P===3)M.push(I,L,C,L,E,R,C,R,N,L,R,C);else if(P===2){let[w,U,F,D,O]=L>=0&&R>=0?[I,E,N,L,R]:R>=0&&C>=0?[E,N,I,R,C]:[N,I,E,C,L];M.push(w,D,O,w,O,F,D,U,O)}else{let[w,U,F,D]=L>=0?[I,E,N,L]:R>=0?[E,N,I,R]:[N,I,E,C];M.push(w,D,F,D,U,F)}}f=M}t.triangles=f}p(Fh,"refineInteriorPostConform");function Oh(n,t){let{uvVerts:e,xyz:i,nrm:s,triangles:r,segmentIndex:o}=t,a=new Float32Array(i.length*3),c=new Float32Array(i.length*3),l=n.reversed?-1:1;for(let m=0;m<i.length;m+=1)a.set(i[m],m*3),c[m*3]=s[m][0]*l,c[m*3+1]=s[m][1]*l,c[m*3+2]=s[m][2]*l;let u=n.reversed?zh(r):Uint32Array.from(r),h=0,f=0;for(let[m,g]of e)h=Math.max(h,Math.abs(m)),f=Math.max(f,Math.abs(g));let d=Dh(u,e,o,Math.max(h,f,1)*1e-7);return{positions:a,normals:c,indices:u,sideOrds:d,uv:e}}p(Oh,"finalizeFaceMesh");function Bh(n,t,e,i=0){let s=p(u=>{let h=t.get(u),f=h?.length?i*.5/h.length:0;return Math.min(.25,Math.max(1e-9,f))},"fractionEps"),r=1e-9,o=p((u,h)=>{let f=t.get(u),d=s(u);return h<=d?0:h>=1-d?f?.closed?0:1:h},"canonicalFraction"),a=new Map,c=p((u,h)=>{let f=a.get(u);f||a.set(u,f=[]),f.push(o(u,h))},"addFraction");for(let{raw:u}of n)for(let h of u.boundary.values())for(let{ord:f,f:d}of h)c(f,d);for(let[u,h]of a){let f=s(u);h.sort((g,_)=>g-_);let d=[];for(let g of h)(!d.length||g-d[d.length-1]>f)&&d.push(g);t.get(u)?.closed&&d.length>1&&1-d[d.length-1]<=f&&d.pop(),a.set(u,d)}let l=p((u,h)=>{let f=a.get(u);if(!f)return h;let d=0,m=f.length-1;for(;d<m;){let _=d+m>>1;f[_]<h?d=_+1:m=_}let g=[f[d],f[d-1]??f[d]];return Math.abs(g[0]-h)<=Math.abs(g[1]-h)?g[0]:g[1]},"representativeOf");for(let{face:u,raw:h}of n){if(u.surface.kind==="plane"){let{origin:x,xdir:v,ydir:y}=u.surface,b=new Map,S=h.loops.map(M=>{let T=[];T.segmentOrds=[],T.segmentMeta=[];for(let I=0;I<M.length;I+=1){let E=M.segmentMeta[I],N=E&&t.get(E.ord);if(!N){T.push(M[I]),T.segmentOrds.push(M.segmentOrds[I]),T.segmentMeta.push(null);continue}let L=p(D=>l(E.ord,o(E.ord,D)),"canonical"),R=p((D,O)=>N.closed&&D===0&&O>.5?1:D,"unwrap"),C=R(L(E.f0),E.f0),P=R(L(E.f1),E.f1),w=s(E.ord),U=a.get(E.ord).filter(D=>D>Math.min(C,P)+w&&D<Math.max(C,P)-w);P<C&&U.reverse();let F=[C,...U,P];for(let D=0;D<F.length;D+=1){if(D+1<F.length&&Math.abs(F[D+1]-F[D])<=w)continue;let O=o(E.ord,F[D]),k=xi(N,O,e),z=tt(k,x),H=[z[0]*v[0]+z[1]*v[1]+z[2]*v[2],z[0]*y[0]+z[1]*y[1]+z[2]*y[2]];D+1<F.length&&(T.push(H),T.segmentOrds.push(E.ord),T.segmentMeta.push({ord:E.ord,f0:F[D],f1:F[D+1]}));let X=`${H[0]}:${H[1]}`,B=b.get(X);B?B.labels.push({ord:E.ord,f:O}):b.set(X,{xyz:k,labels:[{ord:E.ord,f:O}]})}}return T}),A=fo(u,e,S,1/0);A?.triangles.length&&(Object.assign(h,A,{boundary:new Map,loops:S}),h.xyz=A.uvVerts.map(([M,T],I)=>{let E=b.get(`${M}:${T}`);return E&&h.boundary.set(I,E.labels),E?.xyz??ct(u.surface,e,M,T)}),h.nrm=A.uvVerts.map(([M,T])=>wn(u.surface,e,M,T,u.uv,!1)))}for(let[x,v]of h.boundary){for(let S of v)S.f=l(S.ord,o(S.ord,S.f));v.sort((S,A)=>S.ord-A.ord||S.f-A.f);let y=v[0],b=t.get(y.ord);b&&(h.xyz[x]=xi(b,y.f,e))}let f=0;for(let[x,v]of h.uvVerts)f=Math.max(f,Math.abs(x),Math.abs(v));let d=Math.max(f,1)*.01,m=p((x,v)=>Math.abs(h.uvVerts[x][0]-h.uvVerts[v][0])<=d&&Math.abs(h.uvVerts[x][1]-h.uvVerts[v][1])<=d,"uvClose"),g=new Map,_=new Map;for(let x of h.boundary.keys()){let v=h.xyz[x],y=`${v[0]}:${v[1]}:${v[2]}`,b=g.get(y);if(b===void 0){g.set(y,[x]);continue}let S=b.find(A=>m(A,x));S!==void 0?_.set(x,S):b.push(x)}if(_.size){let x=[];for(let v=0;v<h.triangles.length;v+=3){let y=_.get(h.triangles[v])??h.triangles[v],b=_.get(h.triangles[v+1])??h.triangles[v+1],S=_.get(h.triangles[v+2])??h.triangles[v+2];y!==b&&b!==S&&S!==y&&x.push(y,b,S)}h.triangles=x;for(let v of _.keys())h.boundary.delete(v)}}for(let{face:u,raw:h}of n){let{uvVerts:f,xyz:d,nrm:m,boundary:g}=h;if(!g.size)continue;let _=new Map,x=p((C,P)=>C<P?C*4294967296+P:P*4294967296+C,"pairKey");for(let C=0;C<h.triangles.length;C+=3){let[P,w,U]=[h.triangles[C],h.triangles[C+1],h.triangles[C+2]];for(let[F,D]of[[P,w],[w,U],[U,P]]){let O=x(F,D);_.set(O,(_.get(O)||0)+1)}}let v=p(([C,P])=>wn(u.surface,e,C,P,u.uv,!1),"vertexNormal"),y=new Map,b=p((C,P,w,U,F)=>{let D=`${C}:${P.toFixed(12)}:${Math.min(w,U)}:${Math.max(w,U)}`,O=y.get(D);if(O!==void 0)return O;let k=[En(u.surface,f[w][1])?f[U][0]:En(u.surface,f[U][1])?f[w][0]:f[w][0]+F*(f[U][0]-f[w][0]),f[w][1]+F*(f[U][1]-f[w][1])];O=f.length,f.push(k);let z=xi(t.get(C),P,e);return d.push(z),m.push(v(k)),g.set(O,[{ord:C,f:P}]),(h.mintedVerts??=new Set).add(O),y.set(D,O),O},"vertexAt"),S=p((C,P)=>{let w=g.get(C),U=g.get(P);if(!w||!U||_.get(x(C,P))!==1)return null;let F=null,D=null;for(let X of w){let B=U.find(W=>W.ord===X.ord);if(B){F=X,D=B;break}}if(!F||!D)return null;let O=a.get(F.ord);if(!O)return null;let k=t.get(F.ord),z=s(F.ord),H=[];if(k?.closed){let X=(D.f-F.f+1)%1,B=X<=.5,W=B?F.f:D.f,q=B?X:(F.f-D.f+1)%1;if(q<=z*2)return null;for(let $ of O){let J=($-W+1)%1;J>z&&J<q-z&&H.push({f:$,s:B?J/q:1-J/q})}}else{let X=Math.min(F.f,D.f),B=Math.max(F.f,D.f);if(B-X<=z*2)return null;for(let W of O)W>X+z&&W<B-z&&H.push({f:W,s:(W-F.f)/(D.f-F.f)})}return H.length?(H.sort((X,B)=>X.s-B.s),{ord:F.ord,between:H}):null},"insertsFor"),A=[],M=p((C,P,w,U)=>{if(U>24){A.push(C,P,w);return}for(let[F,D,O]of[[C,P,w],[P,w,C],[w,C,P]]){let k=S(F,D);if(k){let z=F;for(let{f:H,s:X}of k.between){let B=b(k.ord,H,F,D,X);M(z,B,O,U+1),z=B}M(z,D,O,U+1);return}}A.push(C,P,w)},"emit"),T=h.triangles;for(let C=0;C<T.length;C+=3)M(T[C],T[C+1],T[C+2],0);h.triangles=A;let I=0;for(let[C,P]of f)I=Math.max(I,Math.abs(C),Math.abs(P));let E=Math.max(I,1)*.01,N=p((C,P)=>Math.abs(f[C][0]-f[P][0])<=E&&Math.abs(f[C][1]-f[P][1])<=E,"uvCloseAfter"),L=new Map,R=new Map;for(let C of g.keys()){let P=d[C],w=`${P[0]}:${P[1]}:${P[2]}`,U=L.get(w);if(U===void 0){L.set(w,[C]);continue}let F=U.find(D=>N(D,C));F!==void 0?R.set(C,F):U.push(C)}if(R.size){let C=[];for(let P=0;P<h.triangles.length;P+=3){let w=R.get(h.triangles[P])??h.triangles[P],U=R.get(h.triangles[P+1])??h.triangles[P+1],F=R.get(h.triangles[P+2])??h.triangles[P+2];w!==U&&U!==F&&F!==w&&C.push(w,U,F)}h.triangles=C;for(let[P,w]of R){let U=g.get(P),F=g.get(w);if(U&&F)for(let D of U)F.some(O=>O.ord===D.ord&&O.f===D.f)||F.push(D);g.delete(P)}}}}p(Bh,"conformBoundaries");function zh(n){let t=new Uint32Array(n.length);for(let e=0;e<n.length;e+=3)t[e]=n[e],t[e+1]=n[e+2],t[e+2]=n[e+1];return t}p(zh,"flipWinding");function po(n,t,e={}){let i=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0],r=[],o=0,a=0;for(let A of n.faces)for(let M of A.loops)for(let T of M)for(let I of[T.range[0],(T.range[0]+T.range[1])/2,T.range[1]]){let[E,N]=Tn(T,t,I),L=ct(A.surface,t,E,N);for(let R=0;R<3;R+=1)L[R]<i[R]&&(i[R]=L[R]),L[R]>s[R]&&(s[R]=L[R])}let c=Math.max(et(tt(s,i)),1e-6),{chordTolerance:l}={...wt,...e},u=new Map;for(let A of n.edges)A.curve&&u.set(A.ord,Rh(A.curve,t,l*c));{let A=c*476837158203125e-21,M=[],T=p(I=>{for(let E of M)if(et(tt(E,I))<=A)return E;return M.push(I),I},"canonicalCorner");for(let I of u.values()){if(I.closed){let E=T(I.points[0]);I.points[0]=E,I.points[I.points.length-1]=E;continue}I.points[0]=T(I.points[0]),I.points[I.points.length-1]=T(I.points[I.points.length-1])}}let h=[];for(let A of n.faces){let M=Uh(A,t,c,e,e.noSharedBoundaries?null:u);M&&h.push({face:A,raw:M})}if(!e.noSharedBoundaries&&!e.noConformPass){Bh(h,u,t,l*c);for(let{face:A,raw:M}of h)Fh(A,M,t,e)}let f=e.collectBoundaryDebug?[]:null;for(let{face:A,raw:M}of h){f&&f.push({faceOrd:A.ord,reversed:!!A.reversed,xyz:M.xyz,triangles:M.triangles.slice(),boundaryByVert:new Map(M.boundary)});let T=Oh(A,M);T&&(r.push({ord:A.ord,color:A.color??null,mesh:T}),o+=T.positions.length/3,a+=T.indices.length)}let d=new Float32Array(o*3),m=new Float32Array(o*3),g=new Float32Array(o),_=new Uint32Array(a),x=new Uint32Array(a),v=[],y=0,b=0;for(let{ord:A,color:M,mesh:T}of r){d.set(T.positions,y*3),m.set(T.normals,y*3),g.fill(A,y,y+T.positions.length/3);for(let I=0;I<T.indices.length;I+=1)_[b+I]=T.indices[I]+y;T.sideOrds&&x.set(T.sideOrds,b),v.push({ord:A,color:M,indexStart:b,indexCount:T.indices.length}),y+=T.positions.length/3,b+=T.indices.length}i=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0];for(let A=0;A<d.length;A+=3)for(let M=0;M<3;M+=1){let T=d[A+M];T<i[M]&&(i[M]=T),T>s[M]&&(s[M]=T)}let S=[];for(let A of n.edges){let M=u.get(A.ord);if(!M)continue;let T=new Float32Array(M.points.length*3);for(let I=0;I<M.points.length;I+=1)T.set(M.points[I],I*3);S.push({ord:A.ord,visibilityClass:A.class,polyline:T})}return{positions:d,normals:m,faceOrds:g,indices:_,sideOrds:x,faceRanges:v,edges:S,bounds:{min:i,max:s},scale:c,...f?{boundaryDebug:f,sharedEdges:u}:{}}}p(po,"tessellateComponent");var _o=1397966164,te=4,yi=1,yo=16*1024,vo=4*1024*1024,kh=/^[0-9a-f]{64}$/,mo=new Set(["chordTolerance","chordToleranceF64","angleTolerance","angleToleranceF64"]),Mo=new Set(["none","feature","tangent","seam","degenerate","boundary","nonManifold","unknown"]);function Yt(n,t){let e=typeof n=="string"?n:"";if(!kh.test(e))throw new TypeError(`${t} must be 64 lowercase hex characters`);return e}p(Yt,"requireDigest");function go(n){if(typeof n!="number"||!Number.isFinite(n)||n<=0)throw new TypeError("tessellation tolerances must be positive finite binary64 values");let t=new Uint8Array(8);return new DataView(t.buffer).setFloat64(0,n,!1),[...t].map(e=>e.toString(16).padStart(2,"0")).join("")}p(go,"float64Hex");var bo=Object.freeze(["chordTolerance","angleTolerance"]),Vh=Object.freeze(Object.keys(wt).filter(n=>!bo.includes(n)));function vi(n={}){let t=Vh.filter(r=>Object.hasOwn(n,r)&&n[r]!==wt[r]);if(t.length)throw new TypeError(`tessellation options are not part of the cache key: ${t.join(", ")}. Keyed options: ${bo.join(", ")}`);let e={...wt,...n},i=e.chordTolerance,s=e.angleTolerance;return Object.freeze({chordTolerance:i,chordToleranceF64:go(i),angleTolerance:s,angleToleranceF64:go(s)})}p(vi,"tessellationQuality");function Te(n,t={}){let e=Yt(n,"surfaceInput"),i=vi(t);return`${e}-t${pe}-p${te}-l${i.chordToleranceF64}-a${i.angleToleranceF64}`}p(Te,"tessellationCacheKey");function So(n,t,e={}){return`${Te(n,e)}-s${Yt(t,"surfaceObject")}`}p(So,"resolvedTessellationIdentity");function Gh(n){return n+3&-4}p(Gh,"align4");function Ns(n){return n!==null&&typeof n=="object"&&!Array.isArray(n)}p(Ns,"isObject");function _i(n,t){return Array.isArray(n)&&n.length===t&&n.every(e=>typeof e=="number"&&Number.isFinite(e))}p(_i,"finiteTuple");function Ls(n){return Number.isSafeInteger(n)&&n>0}p(Ls,"validOrdinal");function Hh(n){if(!Array.isArray(n))return null;let t=new Map;for(let e of n){if(!Array.isArray(e)||e.length!==2||!Ls(e[0])||!Mo.has(e[1])||t.has(e[0]))return null;t.set(e[0],e[1])}return t}p(Hh,"edgeClassMap");function Ao(n){if(!Ns(n?.bounds)||!_i(n.bounds.min,3)||!_i(n.bounds.max,3)||n.bounds.min.some((r,o)=>r>n.bounds.max[o])||typeof n.scale!="number"||!Number.isFinite(n.scale)||n.scale<=0||n.partColor!=null&&!_i(n.partColor,4)||!Array.isArray(n.faceRanges)||!Array.isArray(n.edges))return!1;let t=new Set,e=0;for(let r of n.faceRanges)if(!Ns(r)||!Ls(r.ord)||t.has(r.ord)||!Ye(r.indexStart)||!Ye(r.indexCount)||r.indexStart%3!==0||r.indexCount%3!==0||r.indexStart!==e||r.color!=null&&!_i(r.color,4)||(t.add(r.ord),e+=r.indexCount,!Number.isSafeInteger(e)))return!1;if(e!==n.indexCount)return!1;let i=Hh(n.edgeClasses);if(!i)return!1;let s=new Set;for(let r of n.edges){if(!Ns(r)||!Ls(r.ord)||s.has(r.ord)||!Ye(r.count)||r.count%3!==0||r.visibilityClass!=null&&!Mo.has(r.visibilityClass)||!i.has(r.ord)||r.visibilityClass!=null&&i.get(r.ord)!==r.visibilityClass)return!1;s.add(r.ord)}return!0}p(Ao,"validRenderingMetadata");function To(n){return(Array.isArray(n?.edges)?n.edges:[]).map(e=>[e.ord,String(e.class??"none")])}p(To,"edgeClassesFromSurfIndex");function wo(n,{partColor:t=null,edgeClasses:e=null,surfaceInput:i,surfaceObject:s,tessellation:r={}}={}){let o=Array.isArray(n.edges)?n.edges:[];if(!Array.isArray(n.faceRanges)||!Array.isArray(e))throw new TypeError("TESS v4 requires complete faceRanges and edgeClasses metadata");let a=vi(r),c=Te(i,r),l=Yt(s,"surfaceObject"),u={tessellationInput:c,surfaceInput:Yt(i,"surfaceInput"),surfaceDigest:l,quality:a,tessellatorVersion:pe,payloadVersion:te,partColor:t??null,edgeClasses:e,faceRanges:n.faceRanges,bounds:{min:[...n.bounds.min],max:[...n.bounds.max]},scale:n.scale,positionCount:n.positions.length,normalCount:n.normals.length,faceOrdCount:n.faceOrds.length,indexCount:n.indices.length,sideOrdCount:n.sideOrds.length,edges:o.map(y=>({ord:y.ord,visibilityClass:y.visibilityClass??null,count:y.polyline.length}))};if(!Ao(u))throw new TypeError("TESS v4 requires valid complete rendering metadata");let h=JSON.stringify(u),f=new TextEncoder().encode(h),d=Gh(f.length),m=n.positions.length+n.normals.length+n.faceOrds.length+n.indices.length+n.sideOrds.length+o.reduce((y,b)=>y+b.polyline.length,0),g=new Uint8Array(12+d+m*4),_=new DataView(g.buffer);_.setUint32(0,_o,!0),_.setUint32(4,te,!0),_.setUint32(8,d,!0),g.set(f,12),g.fill(32,12+f.length,12+d);let x=12+d,v=p((y,b)=>{new b(g.buffer,x,y.length).set(y),x+=y.length*4},"append");v(n.positions,Float32Array),v(n.normals,Float32Array),v(n.faceOrds,Float32Array),v(n.indices,Uint32Array),v(n.sideOrds,Uint32Array);for(let y of o)v(y.polyline,Float32Array);return g}p(wo,"encodeComponentTessellation");function Ye(n){return Number.isSafeInteger(n)&&n>=0}p(Ye,"validCount");function Eo({headerBytes:n,arrayBytes:t,faceRangeCount:e,edgeCount:i,edgeClassCount:s,edgeSegmentCount:r}){if(![n,t,e,i,s,r].every(Ye)||n<=0||n>vo||n%4!==0||t%4!==0)throw new TypeError("invalid tessellation size facts");let a=t+8*r+8*n+256*(e+i+s);if(!Number.isSafeInteger(a))throw new TypeError("tessellation decoded size exceeds the safe integer range");return a}p(Eo,"tessellationDecodedBytes");function Wh(n,t={}){try{if(n?.tessellatorVersion!==pe||n?.payloadVersion!==te)return null;let e=Yt(n.surfaceInput,"surfaceInput"),i=Yt(n.surfaceDigest,"surfaceDigest"),s=n.quality;if(!s||typeof s!="object"||Array.isArray(s)||Object.keys(s).length!==mo.size||Object.keys(s).some(l=>!mo.has(l)))return null;let r=vi({chordTolerance:s.chordTolerance,angleTolerance:s.angleTolerance});if(s.chordToleranceF64!==r.chordToleranceF64||s.angleToleranceF64!==r.angleToleranceF64)return null;let o=Te(e,r);if(n.tessellationInput!==o)return null;let a=So(e,i,r);if(t.surfaceInput!==void 0&&Yt(t.surfaceInput,"expected surfaceInput")!==e)return null;let c=t.surfaceObject??t.surfaceDigest;return c!==void 0&&Yt(c,"expected surfaceObject")!==i||t.tessellationInput!==void 0&&String(t.tessellationInput)!==o||t.renderIdentity!==void 0&&String(t.renderIdentity)!==a||t.tessellation!==void 0&&Te(e,t.tessellation)!==o?null:Object.freeze({surfaceInput:e,surfaceObject:i,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:pe,payloadVersion:te})}catch{return null}}p(Wh,"decodedIdentity");function Co(n,t={}){if(!(n instanceof Uint8Array)||n.length<12)return null;let e=new DataView(n.buffer,n.byteOffset,n.byteLength);if(e.getUint32(0,!0)!==_o||e.getUint32(4,!0)!==te)return null;let i=e.getUint32(8,!0);if(i===0||i>vo||i%4!==0||12+i>n.length)return null;let s=JSON.parse(new TextDecoder().decode(n.subarray(12,12+i))),r=Wh(s,t);if(!r||!Array.isArray(s.edges)||!Array.isArray(s.faceRanges)||!Array.isArray(s.edgeClasses))return null;let o=[s.positionCount,s.normalCount,s.faceOrdCount,s.indexCount,s.sideOrdCount],a=s.edges.map(d=>d?.count),c=[...o,...a];if(!c.every(Ye)||s.positionCount%3!==0||s.normalCount!==s.positionCount||s.faceOrdCount*3!==s.positionCount||s.indexCount%3!==0||s.sideOrdCount!==s.indexCount||a.some(d=>d%3!==0)||!Ao(s))return null;let l=c.reduce((d,m)=>d+m,0);if(!Number.isSafeInteger(l)||l>Number.MAX_SAFE_INTEGER/4)return null;let u=l*4;if(n.length!==12+i+u)return null;let h=Object.freeze({headerBytes:i,arrayBytes:u,faceRangeCount:s.faceRanges.length,edgeCount:s.edges.length,edgeClassCount:s.edgeClasses.length,edgeSegmentCount:a.reduce((d,m)=>d+Math.max(0,m/3-1),0)}),f=Eo(h);return{header:s,identity:r,sizes:h,decodedBytes:f}}p(Co,"decodeEnvelope");function Ds(n,t={}){try{let e=Co(n,t);if(!e)return null;let i=Object.freeze({byteLength:n.byteLength,decodedBytes:e.decodedBytes,surfaceInput:e.identity.surfaceInput,surfaceObject:e.identity.surfaceObject,tessellationInput:e.identity.tessellationInput,renderIdentity:e.identity.renderIdentity,quality:e.identity.quality,tessellatorVersion:pe,payloadVersion:te,...e.sizes});for(let s of["byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"])if(t[s]!==void 0&&t[s]!==i[s])return null;return i}catch{return null}}p(Ds,"tessellationPayloadFacts");var xo=new Set(["schemaVersion","object","byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","quality","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"]);function Us(n,t={}){try{if(!n||typeof n!="object"||Array.isArray(n)||Object.keys(n).length!==xo.size||Object.keys(n).some(l=>!xo.has(l))||n.schemaVersion!==yi||n.tessellatorVersion!==pe||n.payloadVersion!==te)return null;let e=Yt(n.surfaceInput,"surfaceInput"),i=Yt(n.surfaceObject,"surfaceObject"),s=Yt(n.object,"object"),r=vi({chordTolerance:n.quality?.chordTolerance,angleTolerance:n.quality?.angleTolerance});if(n.quality?.chordToleranceF64!==r.chordToleranceF64||n.quality?.angleToleranceF64!==r.angleToleranceF64)return null;let o=Te(e,r),a=So(e,i,r);if(n.tessellationInput!==o||n.renderIdentity!==a)return null;let c={headerBytes:n.headerBytes,arrayBytes:n.arrayBytes,faceRangeCount:n.faceRangeCount,edgeCount:n.edgeCount,edgeClassCount:n.edgeClassCount,edgeSegmentCount:n.edgeSegmentCount};return!Ye(n.byteLength)||n.byteLength<=0||n.byteLength!==12+n.headerBytes+n.arrayBytes||n.decodedBytes!==Eo(c)||t.tessellationInput!==void 0&&t.tessellationInput!==o||t.object!==void 0&&t.object!==s||t.surfaceInput!==void 0&&t.surfaceInput!==e||t.surfaceObject!==void 0&&t.surfaceObject!==i?null:Object.freeze({schemaVersion:yi,object:s,byteLength:n.byteLength,decodedBytes:n.decodedBytes,surfaceInput:e,surfaceObject:i,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:pe,payloadVersion:te,...c})}catch{return null}}p(Us,"validateTessellationProbeRow");function Ro(n,t={}){try{let e=Co(n,t);if(!e)return null;let{header:i,identity:s}=e,r=n.byteOffset+12+e.sizes.headerBytes,o=r%4===0,a=p((m,g)=>{let _=o?new g(n.buffer,r,m):new g(n.buffer.slice(r,r+m*4));return r+=m*4,_},"take"),c=a(i.positionCount,Float32Array),l=a(i.normalCount,Float32Array),u=a(i.faceOrdCount,Float32Array),h=a(i.indexCount,Uint32Array),f=a(i.sideOrdCount,Uint32Array),d=i.edges.map(m=>({ord:m.ord,visibilityClass:m.visibilityClass,polyline:a(m.count,Float32Array)}));return{component:{positions:c,normals:l,faceOrds:u,indices:h,sideOrds:f,faceRanges:i.faceRanges,edges:d,bounds:i.bounds,scale:i.scale},partColor:i.partColor??null,edgeClasses:Array.isArray(i.edgeClasses)?i.edgeClasses:null,identity:s}}catch{return null}}p(Ro,"decodeComponentTessellation");var Dy=32*1024*1024;import{createHash as Xh,randomUUID as qh}from"node:crypto";import Et from"node:fs";import Io from"node:os";import Vt from"node:path";var Fs=class extends Error{static{p(this,"TessellationMeshConflictError")}constructor(t="tessellation producer returned different bytes for the same immutable input"){super(t),this.name="TessellationMeshConflictError"}};function Po(n=process.env){return n.CADGEN_MESH_CACHE!=="0"}p(Po,"tessellationCacheEnabled");function No(n=process.env){let t=(n.CADGEN_CACHE_DIR||"").trim();if(t){let e=t.replace(/^~(?=$|[/\\])/,Io.homedir()),i=Vt.resolve(e);return Vt.isAbsolute(e)||(n.CADGEN_CACHE_DIR=i),i}if(process.platform==="win32"){let e=(n.LOCALAPPDATA||"").trim();if(e)return Vt.join(e,"cadgen")}else{let e=(n.XDG_CACHE_HOME||"").trim();if(e)return Vt.join(e,"cadgen")}return Vt.join(Io.homedir(),".cache","cadgen")}p(No,"cadgenCacheRootDir");function $h(n=process.env){return Vt.join(No(n),"index","mesh")}p($h,"tessellationCacheDir");function Mi(n){return Xh("sha256").update(n).digest("hex")}p(Mi,"digestBytes");function Bs(n,t=process.env){return Vt.join(No(t),"objects",n.slice(0,2),n.slice(2))}p(Bs,"objectPath");function Lo(n,t=process.env){return Vt.join($h(t),n)}p(Lo,"indexPath");function Yh(n){return Vt.join(Vt.dirname(n),`.${Vt.basename(n)}.${process.pid}.${qh()}.tmp`)}p(Yh,"tempPath");function Do(n,t){Et.mkdirSync(Vt.dirname(n),{recursive:!0});let e=Yh(n);try{Et.writeFileSync(e,t,{flag:"wx"}),Et.renameSync(e,n)}finally{try{Et.unlinkSync(e)}catch{}}}p(Do,"writeAtomic");function Zh(n){let t=Et.openSync(n,"r");try{let e=Et.fstatSync(t);if(!e.isFile()||e.size<=0||e.size>yo)return null;let i=Buffer.allocUnsafe(e.size);return Et.readSync(t,i,0,i.length,0)!==i.length?null:JSON.parse(i.toString("utf8"))}finally{Et.closeSync(t)}}p(Zh,"readBoundedJson");function Uo(n,t=process.env){if(!Po(t))return null;try{let e=Us(Zh(Lo(n,t)),{tessellationInput:n});if(!e)return null;let i=Et.statSync(Bs(e.object,t));return i.isFile()&&i.size===e.byteLength?e:null}catch{return null}}p(Uo,"probeCachedTessellation");function Os(n,t,e=t){if(!Number.isSafeInteger(t)||t<=0||!Number.isSafeInteger(e)||e<t)return null;let i;try{i=Et.openSync(n,"r");let s=Et.fstatSync(i);if(!s.isFile()||s.size!==t||s.size>e)return null;let r=Buffer.allocUnsafe(t),o=0;for(;o<r.byteLength;){let c=Et.readSync(i,r,o,r.byteLength-o,o);if(c<=0)return null;o+=c}let a=Et.fstatSync(i);return!a.isFile()||a.size!==t?null:new Uint8Array(r.buffer,r.byteOffset,r.byteLength)}catch{return null}finally{if(i!==void 0)try{Et.closeSync(i)}catch{}}}p(Os,"readExactObjectBytes");function zs(n,{expectedObject:t,maxBytes:e,env:i=process.env}={}){let s=Uo(n,i);if(!s||t!==void 0&&s.object!==t)return null;let r=e===void 0?s.byteLength:Number(e);if(!Number.isSafeInteger(r)||r<s.byteLength)return null;let o=Os(Bs(s.object,i),s.byteLength,r);return!o||Mi(o)!==s.object||!Ds(o,s)?null:o}p(zs,"readCachedTessellationBytes");function Jh(n,t){let e=Ds(t,{tessellationInput:n});if(!e)throw new TypeError("invalid TESS v4 payload");let i=Us({schemaVersion:yi,object:Mi(t),...e},{tessellationInput:n});if(!i)throw new TypeError("invalid TESS v4 mesh record");return i}p(Jh,"recordForPayload");function Kh(n,t,e){let i=Bs(n.object,e),s=Os(i,n.byteLength);if(s&&Mi(s)===n.object)return;Do(i,t);let r=Os(i,n.byteLength);if(!r||Mi(r)!==n.object)throw new Error(`tessellation object address mismatch for ${n.object}`)}p(Kh,"putObject");function Fo(n,t,e=process.env){if(!Po(e))return null;let i=t instanceof Uint8Array?t:new Uint8Array(t),s=Jh(n,i),r=Uo(n,e);if(r&&(r.object!==s.object||r.surfaceObject!==s.surfaceObject)&&zs(n,{expectedObject:r.object,env:e}))throw new Fs;return Kh(s,i,e),Do(Lo(n,e),JSON.stringify(s)),s}p(Fo,"writeCachedTessellationBytes");function bi(n){return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}p(bi,"srgbToLinear");function jh(n){return n<=.0031308?n*12.92:1.055*n**(1/2.4)-.055}p(jh,"linearToSrgb");function Qh(n){let t=Math.min(1,Math.max(0,Number(n)||0));return Math.round(Math.min(1,Math.max(0,jh(t)))*255)}p(Qh,"linearChannelToSrgbByte");function ee(n){return!Array.isArray(n)||n.length<3?null:`#${n.slice(0,3).map(e=>Qh(e).toString(16).padStart(2,"0")).join("")}`}p(ee,"linearRgbToHex");var Ze=globalThis.Buffer,tf=typeof TextEncoder<"u"?new TextEncoder:null;function ef(n,t=0){let e=Number(n);return Number.isFinite(e)?e:t}p(ef,"finiteNumber");function Cn(n){return Math.min(Math.max(ef(n),0),1)}p(Cn,"clamp01");function Si(n,t="utf-8"){if(Ze?.from)return Ze.from(String(n),t);if(t!=="utf-8"&&t!=="utf8"){let e=String(n),i=new Uint8Array(e.length);for(let s=0;s<e.length;s+=1)i[s]=e.charCodeAt(s)&255;return i}return tf.encode(String(n))}p(Si,"bytesFromString");function ne(n,t=0){if(Ze?.alloc)return Ze.alloc(n,t);let e=new Uint8Array(n);return t&&e.fill(t),e}p(ne,"allocBytes");function Je(n,t=void 0){if(Ze?.concat)return Ze.concat(n,t);let e=t??n.reduce((r,o)=>r+o.length,0),i=new Uint8Array(e),s=0;for(let r of n)i.set(r,s),s+=r.length;return i}p(Je,"concatBytes");function Ut(n){return new Uint8Array(n.buffer,n.byteOffset,n.byteLength)}p(Ut,"typedArrayBytes");function ks(n){return new DataView(n.buffer,n.byteOffset,n.byteLength)}p(ks,"viewFor");function st(n,t,e){ks(n).setUint16(t,e,!0)}p(st,"writeUInt16LE");function at(n,t,e){ks(n).setUint32(t,e,!0)}p(at,"writeUInt32LE");function Vs(n,t,e){ks(n).setFloat32(t,e,!0)}p(Vs,"writeFloatLE");function Bo(n,t,e,i){let s=String(e).slice(0,i);for(let r=0;r<s.length;r+=1)n[t+r]=s.charCodeAt(r)&127}p(Bo,"writeAscii");function Oo(n,t=32){let e=(4-n.length%4)%4;return e?Je([n,ne(e,t)]):n}p(Oo,"align4Buffer");function we(n,t="model"){return String(n||t).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g,"-")||t}p(we,"sanitizeName");function Gs(n){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let i=0;i<n.length;i+=3)t[0]=Math.min(t[0],n[i]),t[1]=Math.min(t[1],n[i+1]),t[2]=Math.min(t[2],n[i+2]),e[0]=Math.max(e[0],n[i]),e[1]=Math.max(e[1],n[i+1]),e[2]=Math.max(e[2],n[i+2]);return{min:t.map(i=>Number.isFinite(i)?i:0),max:e.map(i=>Number.isFinite(i)?i:0)}}p(Gs,"boundsForPositions");function zo(n,t="#d4d4d8"){let e=String(n||t).trim(),i=/^#(?:[0-9a-fA-F]{3}){1,2}$/.test(e)?e:t,s=i.length===4?`${i[1]}${i[1]}${i[2]}${i[2]}${i[3]}${i[3]}`:i.slice(1);return[parseInt(s.slice(0,2),16)/255,parseInt(s.slice(2,4),16)/255,parseInt(s.slice(4,6),16)/255]}p(zo,"hexToRgb01");function ko(n,t){let e=Oo(Je(t),0);n.buffers=[{byteLength:e.length}];let i=Oo(Si(JSON.stringify(n)),32),s=20+i.length+8+e.length,r=ne(12);at(r,0,1179937895),at(r,4,2),at(r,8,s);let o=ne(8);at(o,0,i.length),at(o,4,1313821514);let a=ne(8);return at(a,0,e.length),at(a,4,5130562),Je([r,o,i,a,e],s)}p(ko,"buildGlb");function nf(n,t){let e=n[t],i=n[t+1],s=n[t+2],r=n[t+3],o=n[t+4],a=n[t+5],c=n[t+6],l=n[t+7],u=n[t+8],h=r-e,f=o-i,d=a-s,m=c-e,g=l-i,_=u-s,x=f*_-d*g,v=d*m-h*_,y=h*g-f*m,b=Math.hypot(x,v,y);return b>1e-12?[x/b,v/b,y/b]:[0,0,1]}p(nf,"triangleNormal");function Vo(n,{name:t="model"}={}){let e=n.positions||new Float32Array,i=Math.floor(e.length/9),s=ne(84+i*50);Bo(s,0,`cad ${we(t)}`,80),at(s,80,i);let r=84;for(let o=0;o<i;o+=1){let a=o*9,c=nf(e,a);for(let l of c)Vs(s,r,l),r+=4;for(let l=0;l<9;l+=1)Vs(s,r,e[a+l]),r+=4;st(s,r,0),r+=2}return s}p(Vo,"meshToBinaryStl");function Ws(n){return String(n??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}p(Ws,"xmlEscape");function Hs(n){let t=Hs.table;if(!t){t=new Uint32Array(256);for(let i=0;i<256;i+=1){let s=i;for(let r=0;r<8;r+=1)s=s&1?3988292384^s>>>1:s>>>1;t[i]=s>>>0}Hs.table=t}let e=4294967295;for(let i of n)e=t[(e^i)&255]^e>>>8;return(e^4294967295)>>>0}p(Hs,"crc32");function Go(n){let t=[],e=[],i=0,s=0,r=33;for(let l of n){let u=Si(l.name),h=l.body instanceof Uint8Array?l.body:Si(String(l.body||"")),f=Hs(h),d=ne(30);at(d,0,67324752),st(d,4,20),st(d,6,0),st(d,8,0),st(d,10,s),st(d,12,r),at(d,14,f),at(d,18,h.length),at(d,22,h.length),st(d,26,u.length),st(d,28,0),t.push(d,u,h);let m=ne(46);at(m,0,33639248),st(m,4,20),st(m,6,20),st(m,8,0),st(m,10,0),st(m,12,s),st(m,14,r),at(m,16,f),at(m,20,h.length),at(m,24,h.length),st(m,28,u.length),st(m,30,0),st(m,32,0),st(m,34,0),st(m,36,0),at(m,38,0),at(m,42,i),e.push(m,u),i+=d.length+u.length+h.length}let o=i,a=Je(e),c=ne(22);return at(c,0,101010256),st(c,4,0),st(c,6,0),st(c,8,n.length),st(c,10,n.length),at(c,12,a.length),at(c,16,o),st(c,20,0),Je([...t,a,c])}p(Go,"zipStore");var Ee=5126,sf=5122,rf=5120,Ho=5123,of=5125,me=34962,Wo=34963,af=4,cf=65535,Ce=32767,Xs=127;function qs(n){return n+3&-4}p(qs,"align4");function qo(n,t){if(n.length>=t)return n;let e=new Uint8Array(t);return e.set(n,0),e}p(qo,"padTo");function Xo(n,t,e,i){if(e===t)return qo(n,qs(n.length));let s=new Uint8Array(i*e);for(let r=0;r<i;r+=1)s.set(n.subarray(r*t,(r+1)*t),r*e);return s}p(Xo,"strideElements");function lf(n,t){let e=n[t],i=n[t+1],s=n[t+2],r=n[t+3],o=n[t+4],a=n[t+5],c=n[t+6],l=n[t+7],u=n[t+8],h=r-e,f=o-i,d=a-s,m=c-e,g=l-i,_=u-s,x=f*_-d*g,v=d*m-h*_,y=h*g-f*m,b=Math.hypot(x,v,y);return b>1e-12?[x/b,v/b,y/b]:[0,0,1]}p(lf,"faceNormal");function uf(n,t,{weldDecimals:e=5}={}){let i=Math.floor(n.length/3),s=10**e,r=p(h=>Math.round(h*s)/s,"q"),o=[],a=[],c=new Uint32Array(i),l=new Map,u=t&&t.length===n.length;for(let h=0;h*9<n.length;h+=1){let f=h*9,d=u?null:lf(n,f);for(let m=0;m<3;m+=1){let g=f+m*3,_=n[g],x=n[g+1],v=n[g+2],y=u?t[g]:d[0],b=u?t[g+1]:d[1],S=u?t[g+2]:d[2],A=`${r(_)},${r(x)},${r(v)},${r(y)},${r(b)},${r(S)}`,M=l.get(A);M===void 0&&(M=o.length/3,l.set(A,M),o.push(_,x,v),a.push(y,b,S)),c[h*3+m]=M}}return{positions:new Float32Array(o),normals:new Float32Array(a),indices:c.subarray(0,Math.floor(n.length/3)*3)}}p(uf,"weldMesh");function hf(n,t){let e=n.length/3,i=new Int16Array(n.length),s=[Math.max(t.max[0]-t.min[0],1e-9),Math.max(t.max[1]-t.min[1],1e-9),Math.max(t.max[2]-t.min[2],1e-9)];for(let r=0;r<e;r+=1)for(let o=0;o<3;o+=1){let a=r*3+o,c=(n[a]-t.min[o])/s[o];i[a]=Math.max(-Ce,Math.min(Ce,Math.round(c*Ce)))}return{array:i,scale:s.map(r=>r/Ce),translation:[t.min[0],t.min[1],t.min[2]]}}p(hf,"quantizePositions");function ff(n){let t=new Int8Array(n.length);for(let e=0;e<n.length;e+=1)t[e]=Math.max(-Xs,Math.min(Xs,Math.round(n[e]*Xs)));return t}p(ff,"quantizeNormals");var df=.42,pf=.03;function Rn(n,t){let e=Number(n?.[t]);return Number.isFinite(e)?Cn(e):null}p(Rn,"finishChannel");function mf(n,t,e=null,i=null){let s=zo(n).map(Cn).map(bi).map(Math.fround),r=Rn(i,"opacity"),o=e==null?r===null?1:r:Cn(e),a=Rn(i,"roughness"),c=Rn(i,"metalness"),l=Rn(i,"clearcoat"),u=Rn(i,"clearcoatRoughness"),h={name:we(t||"material","material"),doubleSided:!0,extras:{cadSourceColor:!0},pbrMetallicRoughness:{baseColorFactor:[...s,o],roughnessFactor:a===null?df:a,metallicFactor:c===null?pf:c}};return o<1&&(h.alphaMode="BLEND"),l!==null&&l>0&&(h.extensions={KHR_materials_clearcoat:{clearcoatFactor:l,...u===null?{}:{clearcoatRoughnessFactor:u}}}),h}p(mf,"materialFor");var gf=[["translation",3,"VEC3"],["rotation",4,"VEC4"],["scale",3,"VEC3"]];function xf(n,{nodeIndexByKey:t,targetCountByKey:e,accessors:i,pushView:s}){let r=[];for(let o of Array.isArray(n)?n:[]){let a=[],c=[],l=new Map,u=p(h=>{let f=l.get(h);if(f!==void 0)return f;if(!h||!h.length)throw new Error("writeGlb: an animation channel needs a non-empty times array");return i.push({bufferView:s(Ut(h)),byteOffset:0,componentType:Ee,count:h.length,type:"SCALAR",min:[h[0]],max:[h[h.length-1]]}),f=i.length-1,l.set(h,f),f},"timeAccessorFor");for(let h of o?.channels||[]){let f=t.get(String(h?.node));if(f===void 0)throw new Error(`writeGlb: animation channel targets node ${JSON.stringify(h?.node)}, which no primitive declared`);let d=u(h?.times||o?.times);if(h?.weights){let m=h?.times||o?.times,g=Number(h.targetCount),_=e.get(String(h.node))||0;if(!Number.isInteger(g)||g<1||g!==_)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} declares ${h.targetCount} morph targets, but its mesh has ${_}`);if(h.weights.length!==m.length*g)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} has ${h.weights.length} scalars for ${m.length} times x ${g} targets`);i.push({bufferView:s(Ut(h.weights)),byteOffset:0,componentType:Ee,count:h.weights.length,type:"SCALAR"}),a.push({input:d,output:i.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:"weights"}})}for(let[m,g,_]of gf){let x=h?.[m];x&&(i.push({bufferView:s(Ut(x)),byteOffset:0,componentType:Ee,count:x.length/g,type:_}),a.push({input:d,output:i.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:m}}))}}c.length&&r.push({name:we(o?.name||"clip","clip"),samplers:a,channels:c})}return r}p(xf,"buildAnimations");function $o(n,t={}){let{preset:e="export",name:i="model",units:s="mm",weldDecimals:r=5,encoder:o=null,occurrenceIdPrefix:a=null,upAxis:c="y",animations:l=null,nodeTransforms:u=null}=t,h=String(c).trim().toLowerCase();if(h!=="y"&&h!=="z")throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(c)}`);let f=String(a||t.sourceKind||we(i,"model")),d=e==="render";if(d&&!o)throw new Error("writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)");if(d&&(l||u))throw new Error("writeGlb: preset 'render' spends every node transform on dequantization, so it carries no animation or node TRS \u2014 use preset 'export' for an animated file");let m=Array.isArray(n?.primitives)&&n.primitives.length?n.primitives:[{positions:n?.positions,normals:n?.normals,color:t.color}],g=[],_=[],x=[],v=[],y=[],b=[],S=new Map,A=0,M=p(w=>{let U=qs(A);U>A&&(g.push(new Uint8Array(U-A)),A=U),g.push(w);let F=A;return A+=w.length,F},"appendBytes"),T=p((w,U)=>{let D={buffer:0,byteOffset:M(w),byteLength:w.length};return U&&(D.target=U),_.push(D),_.length-1},"pushView"),I=p((w,{count:U,stride:F,mode:D,target:O})=>{let k=M(w),z={byteLength:U*F,byteStride:F,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:k,byteLength:w.length,count:U,byteStride:F,mode:D}}};return O&&(z.target=O),_.push(z),_.length-1},"pushCompressedView");for(let w of m){let U=w?.positions instanceof Float32Array?w.positions:new Float32Array(w?.positions||[]);if(!U.length)continue;let F=Array.isArray(w?.targets)&&w.targets.length?w.targets:null;if(F){if(!w?.indices)throw new Error("writeGlb: morph targets need already-indexed input \u2014 a weld can merge two vertices a target moves apart, and the deltas would then be 1:1 with nothing");if(d)throw new Error("writeGlb: preset 'render' quantizes every attribute and carries no morph targets \u2014 use preset 'export' for a deforming file")}let D=w?.indices?{positions:U,normals:w.normals instanceof Float32Array&&w.normals.length===U.length?w.normals:new Float32Array(U.length),indices:w.indices}:uf(U,w?.normals,{weldDecimals:r}),O=D.positions.length/3,k=Gs(D.positions),z=null;if(typeof w?.colorAt=="function"){z=new Uint16Array(O*4);for(let _t=0;_t<O;_t+=1){let De=w.colorAt(D.positions[_t*3],D.positions[_t*3+1],D.positions[_t*3+2],D.normals[_t*3],D.normals[_t*3+1],D.normals[_t*3+2]);for(let Ot=0;Ot<3;Ot+=1)z[_t*4+Ot]=Math.round(bi(Cn(Number(De?.[Ot])||0))*65535);z[_t*4+3]=65535}}let H,X,B=null,W,q,$=null,J=null;if(d){let _t=hf(D.positions,k),De=Xo(Ut(_t.array),6,8,O),Ot=Xo(Ut(ff(D.normals)),3,4,O);H=I(o.encodeVertexBuffer(De,O,8),{count:O,stride:8,mode:"ATTRIBUTES",target:me}),X=I(o.encodeVertexBuffer(Ot,O,4),{count:O,stride:4,mode:"ATTRIBUTES",target:me}),z&&(B=I(o.encodeVertexBuffer(Ut(z),O,8),{count:O,stride:8,mode:"ATTRIBUTES",target:me})),$=_t.scale,J=_t.translation,W={bufferView:H,byteOffset:0,componentType:sf,count:O,type:"VEC3",min:[0,0,0],max:[Ce,Ce,Ce]},q={bufferView:X,byteOffset:0,componentType:rf,count:O,type:"VEC3",normalized:!0}}else H=T(Ut(D.positions),me),X=T(Ut(D.normals),me),z&&(B=T(Ut(z),me)),W={bufferView:H,byteOffset:0,componentType:Ee,count:O,type:"VEC3",min:k.min,max:k.max},q={bufferView:X,byteOffset:0,componentType:Ee,count:O,type:"VEC3"};let K=O<=cf,Q=K?new Uint16Array(D.indices):new Uint32Array(D.indices),nt=K?2:4,yt=d?I(o.encodeIndexBuffer(new Uint8Array(Q.buffer,Q.byteOffset,Q.byteLength),Q.length,nt),{count:Q.length,stride:nt,mode:"TRIANGLES",target:Wo}):T(qo(Ut(Q),qs(Q.byteLength)),Wo);x.push(W);let Jt=x.length-1;x.push(q);let Rt=x.length-1,ft=null;z&&(x.push({bufferView:B,byteOffset:0,componentType:Ho,count:O,type:"VEC4",normalized:!0}),ft=x.length-1),x.push({bufferView:yt,byteOffset:0,componentType:K?Ho:of,count:Q.length,type:"SCALAR"});let ie=x.length-1,At=F?.map((_t,De)=>{let Ot=_t?.positionDeltas;if(!(Ot instanceof Float32Array)||Ot.length!==D.positions.length)throw new Error(`writeGlb: morph target ${De} has ${Ot?.length??"no"} position deltas for ${D.positions.length/3} vertices`);let vr=Gs(Ot);x.push({bufferView:T(Ut(Ot),me),byteOffset:0,componentType:Ee,count:O,type:"VEC3",min:vr.min,max:vr.max});let Mr={POSITION:x.length-1},cn=_t?.normalDeltas;if(cn){if(!(cn instanceof Float32Array)||cn.length!==D.positions.length)throw new Error(`writeGlb: morph target ${De} has ${cn.length} normal deltas for ${D.positions.length/3} vertices`);x.push({bufferView:T(Ut(cn),me),byteOffset:0,componentType:Ee,count:O,type:"VEC3"}),Mr.NORMAL=x.length-1}return Mr})||null;b.push(mf(z?"#ffffff":w?.color,w?.materialName||w?.name,w?.opacity??null,w?.material??null));let _e={attributes:{POSITION:Jt,NORMAL:Rt,...ft===null?{}:{COLOR_0:ft}},indices:ie,material:b.length-1,mode:af,...At?{targets:At}:{}},Ht=w?.node===void 0||w?.node===null?`\0primitive:${S.size}`:String(w.node),It=S.get(Ht);if(!It)It={key:Ht,input:w,primitives:[],quantization:null,targetCount:At?At.length:0},S.set(Ht,It);else{if(It.targetCount!==(At?At.length:0))throw new Error(`writeGlb: node ${JSON.stringify(Ht)} mixes primitives with ${It.targetCount} and ${At?At.length:0} morph targets, and glTF weights are per MESH`);if(d)throw new Error(`writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(Ht)}: each quantized primitive owns its node's transform`)}It.primitives.push(_e),$&&(It.quantization={scale:$,translation:J})}let E=new Map,N=new Map;for(let w of S.values()){N.set(w.key,w.targetCount),v.push({primitives:w.primitives,...w.targetCount?{weights:new Array(w.targetCount).fill(0)}:{}});let U={mesh:v.length-1,name:we(w.input?.name||i,i),extras:{cadOccurrenceId:String(w.input?.occurrenceId||`${f}:${y.length}`),cadSourceKind:t.sourceKind||"mesh",cadUnits:s,cadUpAxis:h}};w.quantization&&(U.scale=w.quantization.scale,U.translation=w.quantization.translation);let F=u instanceof Map?u.get(w.key):null;F&&(F.translation&&(U.translation=[...F.translation]),F.rotation&&(U.rotation=[...F.rotation]),F.scale&&(U.scale=[...F.scale])),E.set(w.key,y.length),y.push(U)}let L=xf(l,{nodeIndexByKey:E,targetCountByKey:N,accessors:x,pushView:T}),R=d?["KHR_mesh_quantization","EXT_meshopt_compression"]:[],C=[...R];b.some(w=>w.extensions?.KHR_materials_clearcoat)&&C.push("KHR_materials_clearcoat");let P={asset:{version:"2.0",generator:"cadgen-js writeGlb"},scene:0,scenes:[{nodes:y.map((w,U)=>U)}],nodes:y,meshes:v,materials:b,bufferViews:_,accessors:x,...L.length?{animations:L}:{}};return C.length&&(P.extensionsUsed=C),R.length&&(P.extensionsRequired=R),ko(P,g)}p($o,"writeGlb");var $s=["stl","glb","3mf"],_f=4194304,Zo="#d4d4d8",Jo=["roughness","metalness","clearcoat","clearcoatRoughness","opacity"];function Ys(n){if(!n||typeof n!="object"||Array.isArray(n))return null;let t={};for(let e of Jo){let i=Number(n[e]);Number.isFinite(i)&&(t[e]=Math.min(1,Math.max(0,i)))}return Object.keys(t).length?t:null}p(Ys,"occurrenceMaterial");function yf(n,t){let e=Ys(n),i=Array.isArray(t)&&t.length>=4&&Number.isFinite(Number(t[3]))?Math.min(1,Math.max(0,Number(t[3]))):1;if(i>=.999)return e;let s=e&&Number.isFinite(Number(e.opacity))?e.opacity:1;return{...e||{},opacity:i*s}}p(yf,"occurrenceMaterialWithSourceAlpha");function Yo(n){return n?`|${Jo.map(t=>t in n?n[t]:"").join(",")}`:""}p(Yo,"materialKey");function Ko(n,t,e,i=Zo){let s=String(t?.component||""),r=/^#[0-9a-fA-F]{6}$/.test(String(t?.baseColor||""))?String(t.baseColor).toUpperCase():ee(t?.color),o=ee(n?.components?.[s]?.color)||null,a=ee(e?.partColor)||null,c=r||o||a||i;return(e?.faceRanges||[]).map(l=>ee(l.color)||c)}p(Ko,"occurrenceFaceRangeColors");function Zs(n,t,e,i,s,r){s[r]=n[0]*t+n[1]*e+n[2]*i+n[3],s[r+1]=n[4]*t+n[5]*e+n[6]*i+n[7],s[r+2]=n[8]*t+n[9]*e+n[10]*i+n[11]}p(Zs,"transformPoint");function Js(n){return n[0]*(n[5]*n[10]-n[6]*n[9])-n[1]*(n[4]*n[10]-n[6]*n[8])+n[2]*(n[4]*n[9]-n[5]*n[8])}p(Js,"determinant3");function Ks(n){let t=n[0],e=n[1],i=n[2],s=n[4],r=n[5],o=n[6],a=n[8],c=n[9],l=n[10],u=r*l-o*c,h=o*a-s*l,f=s*c-r*a,d=t*u+e*h+i*f;if(!Number.isFinite(d)||Math.abs(d)<1e-30)return null;let m=1/d;return[u*m,h*m,f*m,(i*c-e*l)*m,(t*l-i*a)*m,(e*a-t*c)*m,(e*o-i*r)*m,(i*s-t*o)*m,(t*r-e*s)*m]}p(Ks,"normalMatrix3");function js(n){return!Array.isArray(n)||n.length<12?!0:[1,0,0,0,0,1,0,0,0,0,1,0].every((e,i)=>n[i]===e)}p(js,"identityTransform");function Qs(n,t,e={}){let i=e.defaultColor||Zo,s=new Map(Object.entries(n.components||{}).map(([g,_])=>[g,ee(_?.color)])),r=Math.max(1,Math.floor(Number(e.maxPrimitiveTriangles)||_f)),o=e.perOccurrence===!0,a=e.hiddenOccurrenceIds instanceof Set?e.hiddenOccurrenceIds:null,c=e.occurrenceOpacity instanceof Map?e.occurrenceOpacity:null,l=e.occurrenceOverrides instanceof Map?e.occurrenceOverrides:null;if(l&&!o)throw new Error("buildPackageMeshPrimitives: occurrenceOverrides needs perOccurrence \u2014 an override is keyed by occurrence, and the flat soup has no occurrence to key it to");let u=[],h=new Map,f=-1;for(let g of n.occurrences||[]){f+=1;let _=String(g.component||""),x=t.get(_);if(!x)continue;let v=String(g.id||_);if(a?.has(v))continue;let y=/^#[0-9a-fA-F]{6}$/.test(String(g?.baseColor||""))?String(g.baseColor).toUpperCase():ee(g.color),b=s.get(_)||null,S=ee(x.partColor)||null,A=y||b||S||i,M=c?.has(v)?c.get(v):null,T=yf(g.material,g.color),I=String(g.materialId||"").trim(),E=String(g.materialName||I).trim(),N=Yo(T)+(I?`|material:${I}`:""),L=l?.get(v);if(L){L.forEach((U,F)=>{let D=`${String(f).padStart(8,"0")}|${U.color}${Yo(U.material||null)}|${String(F).padStart(4,"0")}`;h.set(D,{override:{...U,node:v,name:String(g.name||v),occurrenceId:v,...I?{materialId:I}:{},...E?{materialName:E}:{},...M==null?{}:{opacity:M}}})});continue}let R=Array.isArray(g.transform)?g.transform:null,C=R===null||js(R),P=!C&&Js(R)<0,w=C?null:Ks(R);for(let U of x.faceRanges||[]){let F=Number(U.indexCount)||0,D=Math.max(0,Math.ceil(F/3));if(!D)continue;let O=ee(U.color)||A,k=(o?`${String(f).padStart(8,"0")}|${O}`:O)+N,z=h.get(k);z||h.set(k,z={color:O,material:T,materialId:I,materialName:E,chunks:[],node:o?v:null,name:o?String(g.name||v):null,occurrenceId:o?v:null,opacity:M});let H=z.chunks[z.chunks.length-1];(!H||H.triangles+D>r)&&(H={triangles:0,floatCount:0,positions:null,normals:null,offset:0},z.chunks.push(H)),H.triangles+=D,H.floatCount+=D*9,u.push({tessellation:x,range:U,color:O,chunk:H,transform:C?null:R,mirrored:P,nm:w})}}for(let g of h.values())for(let _ of g.chunks||[])_.positions=new Float32Array(_.floatCount),_.normals=new Float32Array(_.floatCount);for(let g of u){let{positions:_,normals:x,indices:v}=g.tessellation,{range:y,transform:b,mirrored:S,nm:A}=g,M=g.chunk,T=M.positions,I=M.normals,E=M.offset,N=S?[0,2,1]:[0,1,2];for(let L=y.indexStart;L<y.indexStart+y.indexCount;L+=3)for(let R of N){let C=v[L+R],P=_[C*3],w=_[C*3+1],U=_[C*3+2];b===null?(T[E]=P,T[E+1]=w,T[E+2]=U):Zs(b,P,w,U,T,E);let F=x[C*3],D=x[C*3+1],O=x[C*3+2],k=F,z=D,H=O;A&&(k=A[0]*F+A[1]*D+A[2]*O,z=A[3]*F+A[4]*D+A[5]*O,H=A[6]*F+A[7]*D+A[8]*O);let X=Math.hypot(k,z,H)||1;I[E]=k/X,I[E+1]=z/X,I[E+2]=H/X,E+=3}M.offset=E}let d=[...h.entries()].sort(([g],[_])=>g<_?-1:1).flatMap(([,g])=>g.override?[g.override]:g.chunks.map(_=>({color:g.color,positions:_.positions,normals:_.normals,...g.node===null?{}:{node:g.node,name:g.name,occurrenceId:g.occurrenceId},...g.opacity===null||g.opacity===void 0?{}:{opacity:g.opacity},...g.material===null?{}:{material:g.material},...g.materialId?{materialId:g.materialId}:{},...g.materialName?{materialName:g.materialName}:{}}))).filter(g=>g.indices?g.indices.length>=3:g.positions.length>=9),m=d.reduce((g,_)=>g+(_.indices?_.indices.length/3:_.positions.length/9),0);return{primitives:d,triangleCount:m}}p(Qs,"buildPackageMeshPrimitives");function vf({primitives:n},{name:t="model"}={}){let e=0;for(let r of n)e+=r.positions.length;let i=new Float32Array(e),s=0;for(let r of n)i.set(r.positions,s),s+=r.positions.length;return Vo({positions:i},{name:t})}p(vf,"packageMeshToStl");var In=.001;function Ai(n,t){let e=new Float32Array(n.length);for(let i=0;i<n.length;i+=3)e[i]=n[i]*t,e[i+1]=n[i+2]*t,e[i+2]=-n[i+1]*t;return e}p(Ai,"rotateToYUp");function Mf(n){return n.map(t=>({positionDeltas:Ai(t.positionDeltas,In),...t.normalDeltas?{normalDeltas:Ai(t.normalDeltas,1)}:{}}))}p(Mf,"yUpTargets");function bf(n){let t=n.verify;if(!t)return;let{vertexIds:e,posed:i}=t;for(let s=0;s<i.length;s+=1){let r=n.targets[s].positionDeltas;for(let o=0;o<e.length;o+=1){let a=e[o]*3,c=[i[s][o*3]*In,i[s][o*3+2]*In,-i[s][o*3+1]*In];for(let l=0;l<3;l+=1){let u=n.positions[a+l]+r[a+l];if(Math.abs(u-c[l])>Sf)throw new Error(`packageMeshExport: morph target ${s} of ${n.occurrenceId||n.node} rebuilds vertex ${e[o]} as ${u} where the posed tube is ${c[l]} (axis ${l}) \u2014 base and deltas are not in the same space`)}}}}p(bf,"verifyMorphReconstruction");var Sf=1e-6;function Af(n){return n.map(t=>{let e={...t,positions:Ai(t.positions,In),normals:Ai(t.normals,1),...t.targets?{targets:Mf(t.targets)}:{}};return e.targets&&(bf(e),delete e.verify),e})}p(Af,"yUpPrimitives");function Tf({primitives:n},{name:t="model",animation:e=null}={}){return $o({primitives:Af(n)},{preset:"export",name:t,sourceKind:"step",units:"m",upAxis:"y",...e?{animations:[e],nodeTransforms:e.rest||null}:{}})}p(Tf,"packageMeshToGlb");function wf({primitives:n},{name:t="model"}={}){let e=n.map((c,l)=>`      <base name="material-${l}" displaycolor="${Ws(c.color.toUpperCase())}FF"/>`).join(`
`),i=[],s=[];n.forEach((c,l)=>{let u=[],h=[],f=new Map,d=c.positions,m=p((_,x,v)=>{let y=`${_}:${x}:${v}`,b=f.get(y);return b===void 0&&(b=f.size,f.set(y,b),u.push(`        <vertex x="${_}" y="${x}" z="${v}"/>`)),b},"vertexId");for(let _=0;_<d.length;_+=9){let x=m(d[_],d[_+1],d[_+2]),v=m(d[_+3],d[_+4],d[_+5]),y=m(d[_+6],d[_+7],d[_+8]);x!==v&&v!==y&&y!==x&&h.push(`        <triangle v1="${x}" v2="${v}" v3="${y}"/>`)}let g=l+2;i.push(`    <object id="${g}" type="model" pid="1" pindex="${l}">
      <mesh>
        <vertices>
${u.join(`
`)}
        </vertices>
        <triangles>
${h.join(`
`)}
        </triangles>
      </mesh>
    </object>`),s.push(`    <item objectid="${g}"/>`)});let r=`<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">
  <metadata name="Title">${Ws(t)}</metadata>
  <resources>
    <basematerials id="1">
${e}
    </basematerials>
${i.join(`
`)}
  </resources>
  <build>
${s.join(`
`)}
  </build>
</model>
`;return Go([{name:"[Content_Types].xml",body:`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
`},{name:"_rels/.rels",body:`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
`},{name:"3D/3dmodel.model",body:r}])}p(wf,"packageMeshTo3mf");function jo(n,t,e={}){let i=String(t||"").toLowerCase();if(e.animation&&i!=="glb")throw new Error(`${i||"(no format)"} carries no animation: only glb does \u2014 export the clip as .glb, or drop the animation for a static mesh`);if(i==="stl")return{body:vf(n,e),contentType:"model/stl",extension:".stl"};if(i==="glb")return{body:Tf(n,e),contentType:"model/gltf-binary",extension:".glb"};if(i==="3mf")return{body:wf(n,e),contentType:"model/3mf",extension:".3mf"};throw new Error(`Unsupported package mesh export format: ${t}`)}p(jo,"packageMeshToFormat");var sn=null,Pi=null;function Ma(){return sn?Promise.resolve(sn):(Pi||(Pi=Promise.resolve().then(()=>(Ii(),va)).then(n=>(sn=n,sn)).catch(n=>{throw Pi=null,n})),Pi)}p(Ma,"loadTubeDeformation");function ba(n="a tube deformation"){if(!sn)throw new Error(`${n} needs the tube runtime, which is loaded with the document's animation. Compile clips through compileAnimationSource/loadSourceAnimation, or await loadTubeDeformation() first.`);return sn}p(ba,"requireTubeDeformation");function Sa(n){return!!n&&typeof n=="object"&&!Array.isArray(n)}p(Sa,"isObject");var ed=Math.PI/180;function Aa(n){let t={};for(let[e,i]of Object.entries(Sa(n)?n:{})){if(!Sa(i)||typeof i.update!="function")continue;let s=Number(i.duration);t[String(e)]={id:String(e),label:String(i.label||e),duration:Number.isFinite(s)&&s>0?s:1,loop:i.loop!==!1,update:i.update}}return t}p(Aa,"normalizeAnimationClips");function nd(n){let t=new Map;for(let e of n?.parts||[]){let i=String(e.label||e.name||"").trim();i&&(t.has(i)||t.set(i,[]),t.get(i).push(String(e.id)))}return t}p(nd,"partIdsByLabel");function id(n,t){let e=String(t).replace(/^#/,"").split(",").map(s=>s.trim()).filter(Boolean);if(!e.length||!e.every(s=>/^o[\d.]+$/.test(s)))return null;let i=[];for(let s of n?.parts||[]){let r=String(s.id);e.some(o=>r===o||r.startsWith(`${o}.`))&&i.push(r)}return i.length?i:null}p(id,"partIdsForOccurrenceRefs");function sd(n,t){let e=nd(t),i=new Map,s=new Map,r=new Map;return{model:{get:p(c=>{let l=e.get(String(c).replace(/^#/,""))||e.get(String(c))||id(t,c);if(!l||!l.length){let f=[...e.keys()].sort().join(", ")||"(none)";throw new Error(`animation: no occurrence labeled ${JSON.stringify(c)}; labels: ${f}`)}let u=p(f=>{for(let d of l){let m=i.get(d);i.set(d,m?new n.Matrix4().multiplyMatrices(f,m):f.clone())}},"applyMatrix"),h=p((f,d)=>{for(let m of l){let g=s.get(m)||{};g[f]=d,s.set(m,g)}},"setStyle");return{deformTube(f){let d=ba("deformTube").normalizeTubeDeformation(f);for(let m of l)r.set(m,d);return this},rotate(f,d,m=[0,0,0]){let g=new n.Vector3(f[0],f[1],f[2]).normalize(),_=new n.Matrix4().makeRotationAxis(g,(Number(d)||0)*ed),x=new n.Matrix4().makeTranslation(-m[0],-m[1],-m[2]),v=new n.Matrix4().makeTranslation(m[0],m[1],m[2]);return u(new n.Matrix4().multiplyMatrices(v,new n.Matrix4().multiplyMatrices(_,x))),this},translate(f){return u(new n.Matrix4().makeTranslation(Number(f[0])||0,Number(f[1])||0,Number(f[2])||0)),this},opacity(f){return h("opacity",Math.max(0,Math.min(1,Number(f)))),this},visible(f){return h("visible",!!f),this}}},"handleFor"),labels:p(()=>[...e.keys()].sort(),"labels")},matrices:i,styles:s,deformations:r}}p(sd,"createAnimationFrame");function fr(n,t,e,i){let s=sd(n,t),r=e.duration||1,o=Math.max(0,Number(i)||0);return e.loop!==!1?o=o%r:o=Math.min(o,r),e.update(o,s.model),{matrices:s.matrices,styles:s.styles,deformations:s.deformations}}p(fr,"evaluateAnimationClip");function rd(n){return String(n??"").trim()}p(rd,"normalizeString");function dr(n){return Math.max(Number(n?.duration)||0,.001)}p(dr,"animationClipDuration");function Ta(n){return!n||typeof n!="object"?[]:Object.values(n).filter(t=>t&&typeof t.update=="function").map(t=>({id:String(t.id),label:String(t.label||t.id),duration:dr(t),loop:t.loop!==!1}))}p(Ta,"animationClipList");function wa(n,t){let e=rd(t);if(!e||!n||typeof n!="object")return null;let i=n[e];return i&&typeof i.update=="function"?i:null}p(wa,"findAnimationClip");var Ea=1,Ca=120,Ra=7200;function rn(n){return`${Number(n.toFixed(3))}s`}p(rn,"formatSeconds");function Ia(n,t,{label:e="frame"}={}){let i=n&&typeof n=="object"?n:{},s=Number(i.fps??30);if(!Number.isInteger(s)||s<Ea||s>Ca)throw new Error(`${e} fps must be a whole number ${Ea}..${Ca}, got ${JSON.stringify(i.fps)}`);let r=i.start===void 0||i.start===null?0:Number(i.start);if(!Number.isFinite(r)||r<0)throw new Error(`${e} start must be seconds >= 0, got ${JSON.stringify(i.start)}`);let o=dr(t);if(r>=o)throw new Error(`${e} start ${rn(r)} is at or past the end of a ${rn(o)} clip: every frame would be the same one`);let a=t?.loop!==!1,c=i.seconds===void 0||i.seconds===null?a?o:o-r:Number(i.seconds);if(!Number.isFinite(c)||c<=0)throw new Error(`${e} seconds must be a positive number, got ${JSON.stringify(i.seconds)}`);let l=Math.max(1,Math.round(c*s));if(l>Ra)throw new Error(`${e} ${rn(c)} at ${s} fps schedules ${l} frames, past the ${Ra}-frame ceiling`);let u=[];return!a&&r+c-o>1e-9&&u.push(`${e} covers ${rn(r)}..${rn(r+c)} of a ${rn(o)} clip that does not loop: every frame past its end is the same final pose`),{fps:s,seconds:c,start:r,frameCount:l,warnings:u}}p(Ia,"resolveFramePlan");function Pa(n,t){return n.start+t/n.fps}p(Pa,"framePlanElapsedSec");Ii();var od={Matrix4:gt,Vector3:V},pr=Object.freeze(["opacity","visible"]),Na=Object.freeze(["refuse","morph","rest"]),ad=4,cd=96;function ld(n){let t=Math.max(ad,Math.ceil(cd/n.fps));return{multiple:t,hz:n.fps*t,count:(n.frameCount-1)*t+1}}p(ld,"morphFitGrid");var Ni=.001;function ud(){return new gt().set(Ni,0,0,0,0,0,Ni,0,0,-Ni,0,0,0,0,0,1)}p(ud,"cadToGlbBasis");function hd(){let n=1/Ni;return new gt().set(n,0,0,0,0,0,-n,0,0,n,0,0,0,0,0,1)}p(hd,"glbToCadBasis");var fd=1e-12,dd=new gt().elements;function pd(n){let t=n.elements;for(let e=0;e<16;e+=1)if(Math.abs(t[e]-dd[e])>fd)return!1;return!0}p(pd,"isIdentityMatrix");function md(n){let t=[];for(let e of n?.occurrences||[]){let i=String(e?.id||"").trim(),s=String(e?.component||"").trim(),r=i||s;if(!r)continue;let o=String(e?.name||i||s).trim();t.push({id:r,occurrenceId:r,componentId:s,name:o,label:o})}return{parts:t}}p(md,"animationTargetsFromDescriptor");function Ne(n,t=6){let e=[...n].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}p(Ne,"summarize");function gd(n){let t={translations:[],rotations:[],scales:[],count:0};for(let e=0;e<n;e+=1)gr(t,null);return t}p(gd,"newTrack");var La=new V,Da=new qt,Ua=new V;function gr(n,t){let e=0,i=0,s=0,r=0,o=0,a=0,c=1,l=1,u=1,h=1;if(t!==null&&(t.decompose(La,Da,Ua),{x:e,y:i,z:s}=La,{x:r,y:o,z:a,w:c}=Da,{x:l,y:u,z:h}=Ua),n.count>0){let f=(n.count-1)*4;n.rotations[f]*r+n.rotations[f+1]*o+n.rotations[f+2]*a+n.rotations[f+3]*c<0&&(r=-r,o=-o,a=-a,c=-c)}n.translations.push(e,i,s),n.rotations.push(r,o,a,c),n.scales.push(l,u,h),n.count+=1}p(gr,"appendSample");function mr(n,t,e){for(let i=1;i<e;i+=1)for(let s=0;s<t;s+=1)if(Math.fround(n[i*t+s])!==Math.fround(n[s]))return!0;return!1}p(mr,"varies");function xd(n,t){for(let e=0;e<t*3;e+=1)if(Math.fround(n[e])!==1)return!1;return!0}p(xd,"scaleIsUnit");function Fa(n,t,e,{drop:i=[],deform:s="refuse"}={}){let r=new Set(i.map(E=>String(E).trim())),o=[...r].filter(E=>!pr.includes(E));if(o.length)throw new Error(`animation drop names ${o.sort().join(", ")}, which is not an effect this export can bake static; droppable effects: ${pr.join(", ")}`);let a=String(s||"refuse");if(!Na.includes(a))throw new Error(`animation deform must be one of ${Na.join(", ")}, got ${JSON.stringify(s)}`);let c=md(n),l=ud(),u=hd(),h=new gt,f=new Map,d=new Map,m=new Set,g=new Set,_=new Set,x=new Set,v=new Map,y=new Set,b=a==="morph"?ld(e):{multiple:1,hz:e.fps,count:e.frameCount};for(let E=0;E<b.count;E+=1){let N=Pa(e,E/b.multiple),L=fr(od,c,t,N),R=E%b.multiple===0?E/b.multiple:-1;if(R>=0){for(let[C,P]of L.matrices){let w=f.get(C);if(!w){if(pd(P))continue;w=gd(R),f.set(C,w)}h.multiplyMatrices(l,P).multiply(u),gr(w,h)}for(let C of f.values())C.count===R&&gr(C,null);for(let[C,P]of L.styles)P&&Object.hasOwn(P,"opacity")&&(g.add(C),R===0&&d.set(C,P.opacity)),P&&Object.hasOwn(P,"visible")&&(_.add(C),R===0&&P.visible===!1&&m.add(C))}for(let[C,P]of L.deformations){if(x.add(C),P.braid&&y.add(C),a!=="morph")continue;let w=v.get(C);if(!w)w={rest:P,samples:[]},v.set(C,w);else if(!cr(w.rest,P))throw new Error(`clip ${t.id} changes the REST path of ${C} at ${N.toFixed(4)}s, so its geometry has no single base mesh for morph targets to be deltas against. Author one rest path per tube for the whole clip (move the tube with .translate/.rotate instead), or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);w.samples.push({index:E,timeSec:E/b.hz,deformation:P===w.rest?P:{...P,restSpec:w.rest.restSpec}})}}let S=[];for(let E of pr){let N=E==="opacity"?g:_;if(N.size){if(!r.has(E))throw new Error(`clip ${t.id} animates .${E}() on ${Ne(N)}, and glTF has no standard animated channel for it. Pass drop: ["${E}"] to bake the value at start into the file instead, or animate the occurrence's transform rather than its appearance`);S.push(`.${E}() is not an animated glTF channel: ${Ne(N)} carries its value at start, frozen for the whole clip`)}}if(x.size){if(a==="refuse")throw new Error(`clip ${t.id} deforms tube geometry on ${Ne(x)}: that is per-vertex motion, which a node transform cannot carry. Pass deform: "morph" to bake it as morph targets (bigger file, deformTolerance sets how close they track), deform: "rest" to ship those tubes at their rest shape knowing they do not move, or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);a==="morph"?y.size&&S.push(`${Ne(y)} carries a braid: the strand pattern is a shader, not geometry, so the exported cord has the right shape and motion and a smooth surface`):S.push(`deform: "rest" ships ${Ne(x)} at rest shape: the clip's tube deformation is per-vertex motion this file does not carry`)}let A=[...m].filter(E=>f.has(E));if(A.length){for(let E of A)f.delete(E);S.push(`${Ne(A)} moves in this clip and is hidden at start: dropping .visible() omits the occurrence from the file, and a node that is not there carries no motion`)}let M=new Float32Array(e.frameCount);for(let E=0;E<e.frameCount;E+=1)M[E]=E/e.fps;let T=[],I=new Map;for(let[E,N]of f){let L=new Float32Array(N.translations),R=new Float32Array(N.rotations),C=new Float32Array(N.scales),P=xd(C,N.count);I.set(E,{translation:[L[0],L[1],L[2]],rotation:[R[0],R[1],R[2],R[3]],scale:P?null:[C[0],C[1],C[2]]});let w={node:E};mr(L,3,N.count)&&(w.translation=L),mr(R,4,N.count)&&(w.rotation=R),!P&&mr(C,3,N.count)&&(w.scale=C),(w.translation||w.rotation||w.scale)&&T.push(w)}return T.sort(Oa),{name:t.id,times:M,channels:T,rest:I,statics:{opacity:d,hidden:m},deformations:v,grid:b,warnings:S}}p(Fa,"sampleClipAnimation");function Oa(n,t){return n.node!==t.node?n.node<t.node?-1:1:(n.weights?1:0)-(t.weights?1:0)}p(Oa,"compareChannels");function Ba(n,t){return t?.length?{...n,channels:[...n.channels,...t].sort(Oa)}:n}p(Ba,"withMorphChannels");function za(n,t){let e=n.channels.map(s=>s.node).filter(s=>!t.has(s));if(!e.length)return n;let i=new Map;for(let[s,r]of n.rest)t.has(s)&&i.set(s,r);return{...n,channels:n.channels.filter(s=>t.has(s.node)),rest:i,warnings:[...n.warnings,`${Ne(e)} moves in this clip but has no geometry in the export, so the file carries no node to animate for it`]}}p(za,"restrictAnimationToNodes");Ii();var Li={BufferGeometry:qe,Float32BufferAttribute:ue,Matrix3:Y,Vector3:V},_d=1,xr=512*1024*1024,ka=16,Va=5,yd=128,vd=512,Di=new gt;function Ga(n,t=6){let e=[...n].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}p(Ga,"summarize");function Ha(n){return n>=1024**3?`${(n/1024**3).toFixed(2)} GiB`:`${(n/1024**2).toFixed(1)} MiB`}p(Ha,"formatBytes");function Md(n,t){let e=Array.isArray(n.transform)?n.transform:null,i=e===null||js(e),s=!i&&Js(e)<0,r=i?null:Ks(e),o=t.positions,a=t.normals,c=Math.floor(o.length/3),l=new Float32Array(o.length),u=new Float32Array(o.length);for(let v=0;v<c;v+=1){let y=v*3;i?(l[y]=o[y],l[y+1]=o[y+1],l[y+2]=o[y+2]):Zs(e,o[y],o[y+1],o[y+2],l,y);let b=a[y],S=a[y+1],A=a[y+2],M=b,T=S,I=A;r&&(M=r[0]*b+r[1]*S+r[2]*A,T=r[3]*b+r[4]*S+r[5]*A,I=r[6]*b+r[7]*S+r[8]*A);let E=Math.hypot(M,T,I)||1;u[y]=M/E,u[y+1]=T/E,u[y+2]=I/E}let h=t.faceRanges||[],f=0;for(let v of h)f+=Math.floor((Number(v.indexCount)||0)/3);let d=new Uint32Array(f*3),m=new Uint32Array(f),g=s?[0,2,1]:[0,1,2],_=0;h.forEach((v,y)=>{let b=Number(v.indexStart)||0,S=Number(v.indexCount)||0;for(let A=b;A+2<b+S;A+=3)d[_*3]=t.indices[A+g[0]],d[_*3+1]=t.indices[A+g[1]],d[_*3+2]=t.indices[A+g[2]],m[_]=y,_+=1});let x=new qe;return x.setAttribute("position",new Lt(l,3)),x.setAttribute("normal",new Lt(u,3)),x.setIndex(new Lt(d,1)),{geometry:x,triangleRange:m}}p(Md,"occurrenceWorldGeometry");function bd(n){let t=n.values,e=Math.floor(t.length/8),i=new Map;for(let a=0;a<e;a+=1){let c=a*8,l=t[c],u=i.get(l);if(!u){i.set(l,[t[c+1],t[c+1],t[c+2],t[c+2],t[c+3],t[c+3]]);continue}for(let h=0;h<3;h+=1){let f=t[c+1+h];f<u[h*2]&&(u[h*2]=f),f>u[h*2+1]&&(u[h*2+1]=f)}}let s=[...i.keys()].sort((a,c)=>a-c),r=new Uint32Array(s.length+1),o=[];return s.forEach((a,c)=>{let l=i.get(a),u=[0,1,2].map(h=>l[h*2]===l[h*2+1]?[l[h*2]]:[l[h*2],l[h*2+1]]);for(let h of u[0])for(let f of u[1])for(let d of u[2])o.push(h,f,d);r[c+1]=o.length/3}),{fractions:Float64Array.from(s),cornerOffset:r,uva:Float64Array.from(o)}}p(bd,"boundsForFractions");function Wa(n,t,e){let i=t.path,s=(t.twistDeg||0)*Math.PI/180,r=Math.cos(s),o=Math.sin(s);for(let a=0;a<n.fractions.length;a+=1){let c=nn(i,n.fractions[a]*i.length),l=c.point,u=c.normal,h=c.binormal,f=c.tangent;for(let d=n.cornerOffset[a];d<n.cornerOffset[a+1];d+=1){let m=d*3,g=n.uva[m],_=n.uva[m+1],x=n.uva[m+2],v=r*g-o*_,y=o*g+r*_;e[m]=l[0]+u[0]*v+h[0]*y+f[0]*x,e[m+1]=l[1]+u[1]*v+h[1]*y+f[1]*x,e[m+2]=l[2]+u[2]*v+h[2]*y+f[2]*x}}return e}p(Wa,"poseCorners");function Sd(n,t,e,i){let s=0;for(let r=0;r<e.length;r+=3){let o=e[r]-(n[r]+(t[r]-n[r])*i),a=e[r+1]-(n[r+1]+(t[r+1]-n[r+1])*i),c=e[r+2]-(n[r+2]+(t[r+2]-n[r+2])*i),l=o*o+a*a+c*c;l>s&&(s=l)}return Math.sqrt(s)}p(Sd,"blendDeviation");function Ad(n,t,e){let i=n.length,s=[0];if(i<2)return s;let r=0,o=Wa(t,Zt(n[0]),new Float64Array(t.uva.length)),a=o,c=[],l=!0;for(let u=1;u<i;u+=1){let h=Pe(n[u],n[u-1])?a:Wa(t,Zt(n[u]),new Float64Array(t.uva.length));a=h,c.push({index:u,pose:h}),l=l&&Pe(n[u],n[r]);let f=!1;if(!l){let g=u-r;for(let _ of c){if(_.index===u)continue;let x=(_.index-r)/g;if(Sd(o,h,_.pose,x)>e){f=!0;break}}}if(!f&&c.length<yd)continue;let d=f?u-1:u,m=c.find(g=>g.index===d);s.push(d),r=d,o=m.pose,c=c.filter(g=>g.index>d),l=c.every(g=>Pe(n[g.index],n[r]))}return s[s.length-1]!==i-1&&s.push(i-1),s}p(Ad,"fitTargetTimes");function Td(n,t,e){let i=n.geometry.index,s=Math.floor(i.count/3),r=n.sourceTriangles,o=new Map;for(let a=0;a<s;a+=1){let c=r?r[a]:a,l=e[t[c]]||e[0],u=o.get(l);u||o.set(l,u=[]),u.push(a)}return[...o.entries()].map(([a,c])=>{let l=new Uint32Array(c.length*3),u=new Map,h=0;c.forEach((d,m)=>{for(let g=0;g<3;g+=1){let _=i.getX(d*3+g),x=u.get(_);x===void 0&&(x=h,h+=1,u.set(_,x)),l[m*3+g]=x}});let f=new Uint32Array(h);for(let[d,m]of u)f[m]=d;return{color:a,indices:l,vertexIds:f,slotOf:u}})}p(Td,"partitionByColor");function On(n,t){let e=new Float32Array(t.length*3);for(let i=0;i<t.length;i+=1){let s=t[i]*3;e[i*3]=n[s],e[i*3+1]=n[s+1],e[i*3+2]=n[s+2]}return e}p(On,"gather");function wd(n){let t=Math.max(1,Math.min(n,vd)),e=new Uint32Array(t);for(let i=0;i<t;i+=1)e[i]=Math.floor(i*n/t);return e}p(wd,"verifySampleIds");function Ed(n,t){let e=0;for(let i=0;i<n.length;i+=3){let s=n[i],r=n[i+1],o=n[i+2],a=t[i],c=t[i+1],l=t[i+2],u=Math.hypot(s,r,o)*Math.hypot(a,c,l);if(u<1e-12)continue;let h=Math.min(1,Math.max(-1,(s*a+r*c+o*l)/u)),f=Math.acos(h)*180/Math.PI;f>e&&(e=f)}return e}p(Ed,"maxNormalDegrees");function Xa(n,t,e,i={}){let{toleranceMm:s=_d,grid:r,defaultColor:o=null,clipId:a="clip",maxRuntimeBytes:c=xr}=i,l=Number(s);if(!(l>0))throw new Error(`morph deformTolerance must be a positive number of millimetres, got ${s}`);let u=[],h=new Map,f=[];if(!e?.size)return{overrides:h,channels:f,warnings:u,stats:null};let d=[],m=[];for(let v of n.occurrences||[]){let y=String(v.component||""),b=String(v.id||y),S=e.get(b);if(!S)continue;let A=t.get(y);if(!A||!A.positions?.length){m.push(b);continue}d.push({occurrence:v,occurrenceId:b,tessellation:A,entry:S})}if(m.length&&u.push(`${Ga(m)} deforms in this clip but tessellated to nothing, so the file carries no geometry to morph for it`),!d.length)return{overrides:h,channels:f,warnings:u,stats:null};let g=[],_=0;for(let v of d){let y=v.entry.samples[0].deformation,{geometry:b,triangleRange:S}=Md(v.occurrence,v.tessellation),A=hr(Li,b,Zt(y),Di),M={restSpec:y.restSpec,pathSpec:y.restSpec,twistDeg:0,maxSegmentLength:y.maxSegmentLength,braid:y.braid},T=new Array(r.count).fill(M);for(let L of v.entry.samples)T[L.index]=L.deformation;let I=bd(A.mapping),E=Ad(T,I,l),N=A.vertexCount;g.push({...v,bake:A,model:I,poses:T,keys:E,triangleRange:S,vertexCount:N}),_+=N*Math.max(0,E.length-1)*2*ka}if(_>Math.min(c,xr)){let v=g.reduce((b,S)=>b+Math.max(0,S.keys.length-1),0),y=g.reduce((b,S)=>b+S.vertexCount,0);throw new Error(`clip ${a} needs ${v} morph targets over ${g.length} tubes (${y} refined vertices) to hold ${l}mm, which is ${Ha(_)} of morph texture at playback \u2014 past the ${Ha(Math.min(c,xr))} ceiling, and it is the GPU number rather than the file size that decides whether the file opens. Raise deformTolerance (the target count falls as its square root), shorten seconds, coarsen --mesh-tolerance so the tubes carry fewer vertices, or coarsen the clip's own maxSegmentLength`)}let x={toleranceMm:l,nodes:0,targets:0,bytes:0,runtimeBytes:0,refinedTriangles:0,deviationMm:0,normalsOmitted:[]};for(let v of g){let{bake:y,poses:b,keys:S,vertexCount:A,occurrenceId:M}=v,T=new ue(new Float32Array(A*3),3),I=new ue(new Float32Array(A*3),3);Fn(Li,y,Zt(b[S[0]]),Di,T,I);let E=Float32Array.from(T.array),N=Float32Array.from(I.array),L=wd(A),R=[],C=[],P=[],w=0;for(let B=1;B<S.length;B+=1){Fn(Li,y,Zt(b[S[B]]),Di,T,I);let W=new Float32Array(A*3),q=new Float32Array(A*3);for(let $=0;$<W.length;$+=1)W[$]=T.array[$]-E[$],q[$]=I.array[$]-N[$];R.push(W),C.push(q),P.push(On(T.array,L)),w=Math.max(w,Ed(N,I.array))}let U=w>=Va;!U&&R.length&&x.normalsOmitted.push(M);let F=new Int32Array(S.length).fill(-1),D=[];for(let B=1;B<S.length;B+=1){let W=R[B-1],q=!1;for(let $=0;$<W.length;$+=1)if(W[$]!==0){q=!0;break}q&&(F[B]=D.length,D.push(B-1))}let O=Cd(v,{basePositions:E,deltaPositions:R,grid:r,tolerance:l,posed:T,posedNormals:I});x.deviationMm=Math.max(x.deviationMm,O);let k=Ko(n,v.occurrence,v.tessellation,o||void 0),z=Ys(v.occurrence.material),X=Td(y,v.triangleRange,k).map(B=>{let W=B.vertexIds,q=D.map(K=>({positionDeltas:On(R[K],W),...U?{normalDeltas:On(C[K],W)}:{}})),$=[],J=[];return L.forEach((K,Q)=>{let nt=B.slotOf.get(K);nt!==void 0&&($.push(nt),J.push(Q))}),{color:B.color,positions:On(E,W),normals:On(N,W),indices:B.indices,...z===null?{}:{material:z},...q.length?{targets:q}:{},...q.length&&$.length?{verify:{vertexIds:Uint32Array.from($),posed:D.map(K=>{let Q=P[K],nt=new Float32Array(J.length*3);return J.forEach((yt,Jt)=>{nt[Jt*3]=Q[yt*3],nt[Jt*3+1]=Q[yt*3+1],nt[Jt*3+2]=Q[yt*3+2]}),nt})}}:{}}});h.set(M,X),x.nodes+=1,x.targets+=D.length,x.refinedTriangles+=Math.floor(y.geometry.index.count/3);for(let B of X){let W=B.positions.length/3;x.bytes+=W*D.length*(U?24:12),x.runtimeBytes+=W*D.length*(U?2:1)*ka}if(D.length){let B=new Float32Array(S.length),W=new Float32Array(S.length*D.length);for(let q=0;q<S.length;q+=1)B[q]=S[q]/r.hz,F[q]>=0&&(W[q*D.length+F[q]]=1);f.push({node:M,times:B,weights:W,targetCount:D.length})}}return x.normalsOmitted.length&&u.push(`${Ga(x.normalsOmitted)} turns by less than ${Va}\xB0 over this clip, so its morph targets carry positions only and its shading rides the base normals`),{overrides:h,channels:f,warnings:u,stats:x}}p(Xa,"buildTubeMorphTargets");function Cd(n,{basePositions:t,deltaPositions:e,grid:i,tolerance:s,posed:r,posedNormals:o}){let{bake:a,poses:c,keys:l,occurrenceId:u}=n;if(l.length<2)return 0;let h=0,f=0;for(let d=0;d<c.length;d+=i.multiple){for(;f+2<l.length&&l[f+1]<=d;)f+=1;let m=l[f],g=l[f+1],_=g===m?0:(d-m)/(g-m);Fn(Li,a,Zt(c[d]),Di,r,o);let x=f>=1?e[f-1]:null,v=e[f];for(let y=0;y<t.length;y+=3){let b=0;for(let S=0;S<3;S+=1){let A=t[y+S]+(x?x[y+S]*(1-_):0)+(v?v[y+S]*_:0),M=r.array[y+S]-A;b+=M*M}b>h&&(h=b)}}if(h=Math.sqrt(h),h>s+.001)throw new Error(`morph fit for ${u} leaves ${h.toFixed(4)}mm between the baked targets and the clip's own deformation, past the ${s}mm it was fitted to`);return h}p(Cd,"verifyMorphFit");var _r=Object.freeze(["clips"]);function Rd(n){if(typeof Buffer<"u")return Buffer.from(n,"utf8").toString("base64");let t=new TextEncoder().encode(n),e="";for(let i of t)e+=String.fromCharCode(i);return btoa(e)}p(Rd,"base64Utf8");async function Id(n,{name:t="embedded animation"}={}){let e=String(n||""),i=`data:text/javascript;base64,${Rd(e)}`;try{return await import(i)}catch(s){let r=s instanceof Error?s.message:String(s);throw new Error(`${t}: ${r}`)}}p(Id,"importAnimationModule");function Pd(n,{name:t="embedded animation"}={}){let i=Object.keys(n||{}).filter(s=>s!=="default").filter(s=>!_r.includes(s));if(i.length)throw new Error(`${t}: unknown export${i.length===1?"":"s"} ${i.join(", ")} \u2014 the renderer understands: ${_r.join(", ")}`);if("default"in(n||{}))throw new Error(`${t}: a default export is not an animation-module export \u2014 use named exports (${_r.join(", ")})`);return{clips:Aa(n?.clips)}}p(Pd,"compileAnimationModule");async function qa(n,t={}){let[e]=await Promise.all([Id(n,t),Ma()]);return Pd(e,t)}p(qa,"compileAnimationSource");function Nd(n){let t={},e=[],i=[],s=[],r=[],o={chord:void 0,angle:void 0};for(let a=0;a<n.length;a+=1){let c=n[a];if(!c.startsWith("--"))continue;let l=n[a+1],u=l===void 0||l.startsWith("--")?"true":l;u!=="true"&&(a+=1),c==="--format"?(e.push(u),s.push({chord:void 0,angle:void 0}),r.push(void 0)):c==="--out"?i.push(u):c==="--chord-tolerance"?(s.length?s[s.length-1]:o).chord=u:c==="--angle-tolerance"?(s.length?s[s.length-1]:o).angle=u:c==="--animation"?(r.length||Ct("--animation must follow the --format/--out pair it animates"),r[r.length-1]=u):t[c.slice(2)]=u}return{args:t,formats:e,outs:i,pairTolerances:s,pairAnimations:r,defaults:o}}p(Nd,"parseArgs");function Ct(n){process.stdout.write(`${JSON.stringify({ok:!1,error:String(n)})}
`),process.exit(1)}p(Ct,"fail");function Ld(n,t,e,i){let s=String(e?.surfaceInput||""),r=String(e?.surfaceObject||""),o=Te(s,i),a=Ro(zs(o),{surfaceInput:s,surfaceObject:r,tessellationInput:o,tessellation:i});if(a)return{...a.component,partColor:a.partColor};let c=String(e?.surf||"");if(!c)throw new Error(`component ${t} has no surf payload`);let l=on.readFileSync(an.join(n,c)),{index:u,floats:h}=Sr(l.buffer.slice(l.byteOffset,l.byteOffset+l.byteLength)),f=po(u,h,i),d=Array.isArray(u.partColor)?u.partColor:null;return Fo(o,wo(f,{surfaceInput:s,surfaceObject:r,tessellation:i,partColor:d,edgeClasses:To(u)})),{...f,partColor:d}}p(Ld,"tessellationForComponent");var{args:Bn,formats:yr,outs:Ja,pairTolerances:$a,pairAnimations:Ya,defaults:Za}=Nd(process.argv.slice(2)),Ui=String(Bn["package-dir"]||"");(!Ui||!an.isAbsolute(Ui))&&Ct("--package-dir must be an absolute render-package directory");(!yr.length||yr.length!==Ja.length)&&Ct("--format and --out must be given as one or more ordered pairs");var Le=yr.map((n,t)=>{let e=$a[t].chord??Za.chord,i=$a[t].angle??Za.angle,s={...wt};e!==void 0&&(s.chordTolerance=Number(e)),i!==void 0&&(s.angleTolerance=Number(i));let r=null;if(Ya[t]!==void 0){try{r=JSON.parse(String(Ya[t]))}catch(o){Ct(`--animation must be a JSON object: ${o?.message||o}`)}(!r||typeof r!="object"||Array.isArray(r))&&Ct("--animation must be a JSON object")}return{format:String(n).toLowerCase(),out:String(Ja[t]),options:s,animation:r,groupKey:`${s.chordTolerance}:${s.angleTolerance}`}});for(let n of Le)(!n.out||!an.isAbsolute(n.out))&&Ct("--out must be an absolute output path"),$s.includes(n.format)||Ct(`--format must be one of ${$s.join(", ")}`),(!(n.options.chordTolerance>0)||!(n.options.angleTolerance>0))&&Ct("tolerances must be positive numbers"),n.animation&&n.format!=="glb"&&Ct(`${n.format} carries no animation: only glb does`),n.animation&&!String(n.animation.clip||"").trim()&&Ct("--animation must name a clip");new Set(Le.map(n=>n.out)).size!==Le.length&&Ct("--out paths must be distinct");var Dd=String(Bn.name||an.basename(Le[0].out).replace(/\.[^.]+$/,"")||"model"),Fi=Bn["default-color"]?String(Bn["default-color"]):null;Fi!==null&&!/^#[0-9a-fA-F]{6}$/.test(Fi)&&Ct("--default-color must be #rrggbb");var Ka=String(Bn["animation-source"]||"");Le.some(n=>n.animation)&&!Ka&&Ct("--animation needs --animation-source: the clips live in the document sidecar");async function Ud(n){let t=on.readFileSync(n,"utf8");return(await qa(t,{name:"embedded animation"})).clips}p(Ud,"loadClips");function Fd(n,t,e){let i=String(n.animation.clip),s=wa(t,i);if(!s){let a=Ta(t).map(c=>c.id);throw new Error(a.length?`Unknown animation clip: ${i}. This model declares: ${a.join(", ")}`:`Unknown animation clip: ${i}. This model declares no animation clips`)}let r=Ia(n.animation,s,{label:"animation"}),o=Fa(e,s,r,{drop:Array.isArray(n.animation.drop)?n.animation.drop:[],deform:n.animation.deform});return{clip:s,plan:r,sampled:o}}p(Fd,"sampleJobAnimation");try{let n=JSON.parse(on.readFileSync(an.join(Ui,"assembly.json"),"utf8")),t=n.components||{},e=new Set((n.occurrences||[]).map(o=>String(o.component||""))),i=Le.some(o=>o.animation)?await Ud(Ka):null,s=new Map;Le.forEach((o,a)=>{s.has(o.groupKey)||s.set(o.groupKey,{options:o.options,members:[]}),s.get(o.groupKey).members.push({job:o,index:a})});let r=[];for(let o of s.values()){let a=new Map;for(let u of e){if(!t[u])throw new Error(`descriptor names unknown component ${u}`);a.set(u,Ld(Ui,u,t[u],o.options))}let c=Fi?{defaultColor:Fi.toLowerCase()}:{},l=null;for(let{job:u,index:h}of o.members){let f,d=null,m=null;if(u.animation){let{plan:x,sampled:v}=Fd(u,i,n),y=Xa(n,a,v.deformations,{toleranceMm:u.animation.deformTolerance,grid:v.grid,clipId:v.name,...c.defaultColor?{defaultColor:c.defaultColor}:{}});f=Qs(n,a,{...c,perOccurrence:!0,hiddenOccurrenceIds:v.statics.hidden,occurrenceOpacity:v.statics.opacity,occurrenceOverrides:y.overrides}),d=za(Ba(v,y.channels),new Set(f.primitives.map(b=>b.node).filter(Boolean))),m={clip:d.name,fps:x.fps,samples:x.frameCount,seconds:x.seconds,start:x.start,channels:d.channels.length,...y.stats?{deform:{mode:"morph",nodes:y.stats.nodes,targets:y.stats.targets,bytes:y.stats.bytes,runtimeBytes:y.stats.runtimeBytes,refinedTriangles:y.stats.refinedTriangles,deviationMm:Number(y.stats.deviationMm.toFixed(4)),toleranceMm:y.stats.toleranceMm,fitGridHz:v.grid.hz}}:{},warnings:[...x.warnings,...d.warnings,...y.warnings]}}else l=l||Qs(n,a,c),f=l;if(!f.triangleCount)throw new Error("tree produced no triangles");let{body:g}=jo(f,u.format,{name:Dd,animation:d});on.mkdirSync(an.dirname(u.out),{recursive:!0});let _=`${u.out}.${process.pid}.tmp`;on.writeFileSync(_,g),on.renameSync(_,u.out),r[h]={path:u.out,format:u.format,triangleCount:f.triangleCount,...m?{animation:m}:{}}}}process.stdout.write(`${JSON.stringify({ok:!0,files:r})}
`)}catch(n){Ct(n?.message||n)}
/*! Bundled license information:

three/build/three.core.js:
three/build/three.module.js:
  (**
   * @license
   * Copyright 2010-2026 Three.js Authors
   * SPDX-License-Identifier: MIT
   *)
*/
