import test from 'node:test';
import assert from 'node:assert/strict';
import {exteriorPoint,weatherStyle,ExteriorWeather} from '../src/deep_empathy/web/bookstore-weather.mjs';
import * as THREE from '../src/deep_empathy/web/vendor/three/three.module.js';
test('all precipitation anchors stay outside the room including wind and snow sway',()=>{
 for(let i=0;i<10000;i++){const[x,z]=exteriorPoint();assert.ok((x< -8.3||x>6.3)||z>4.4);assert.ok((x+.15< -8.25||x+.15>6.25)||z>4.4);}
});
test('weather changes effects without enabling indoor lighting or stacking particle groups',()=>{
 const scene=new THREE.Scene(),fx=new ExteriorWeather(scene),count=scene.children.length;
 fx.set({kind:'rain',wind_ms:3},false);fx.tick(.016,1);assert.ok(fx.rain.visible);assert.equal(fx.snow.visible,false);
 fx.set({kind:'snow'},true);fx.tick(.016,2);assert.ok(fx.snow.visible);assert.equal(fx.rain.visible,false);
 fx.set({kind:'clear'},true);assert.equal(fx.ground.visible,false);assert.equal(fx.rain.visible,false);
 assert.equal(scene.children.length,count);assert.equal(scene.children.some(x=>x.isLight),false);
 assert.ok(weatherStyle('storm').light<weatherStyle('clear').light);
});
test('rain reduces direct-to-diffuse contrast and cast shadows rather than simply dimming both lights',async()=>{
 const {applyWeatherLighting}=await import('../src/deep_empathy/web/bookstore-weather.mjs');
 const ambient=new THREE.HemisphereLight(),sun=new THREE.DirectionalLight();
 applyWeatherLighting(ambient,sun,'clear');const clearContrast=sun.intensity/ambient.intensity,clearShadow=sun.shadow.intensity,clearRadius=sun.shadow.radius;
 for(const kind of ['rain','storm','overcast','fog','snow']){
  applyWeatherLighting(ambient,sun,kind);
  assert.ok(sun.intensity/ambient.intensity<clearContrast/4,kind);
  assert.ok(sun.shadow.intensity<clearShadow/4,kind);
  assert.ok(sun.shadow.radius>clearRadius,kind);
 }
 applyWeatherLighting(ambient,sun,'rain',false);assert.equal(sun.intensity,0);assert.equal(sun.castShadow,false);assert.equal(sun.shadow.intensity,0);assert.equal(ambient.intensity,.07);
 applyWeatherLighting(ambient,sun,'clear');assert.equal(sun.shadow.intensity,clearShadow);assert.equal(sun.intensity/ambient.intensity,clearContrast);
 for(let i=0;i<10;i++)applyWeatherLighting(ambient,sun,'clear');assert.equal(sun.intensity/ambient.intensity,clearContrast);
});

test('wet weather keeps indoor diffuse light warm and bright while shop is open',async()=>{
 const {applyWeatherLighting}=await import('../src/deep_empathy/web/bookstore-weather.mjs');
 const ambient=new THREE.HemisphereLight(),sun=new THREE.DirectionalLight();
 for(const kind of ['overcast','rain','snow']){
  applyWeatherLighting(ambient,sun,kind,true);
  assert.ok(ambient.intensity>=3.3);
  assert.ok(ambient.color.r>ambient.color.b);
  assert.ok(ambient.groundColor.r>ambient.groundColor.b);
  assert.ok(sun.shadow.intensity<=.1);
  applyWeatherLighting(ambient,sun,kind,false);assert.equal(ambient.intensity,.07);assert.equal(sun.intensity,0);
 }
});

test('precipitation uses an indoor silhouette exclusion stencil',()=>{
 const fx=new ExteriorWeather(new THREE.Scene());fx.set({kind:'rain'},true);
 assert.ok(fx.indoorMask.visible);assert.equal(fx.indoorMask.material.colorWrite,false);
 assert.equal(fx.indoorMask.material.stencilZPass,THREE.ReplaceStencilOp);
 for(const effect of [fx.rain,fx.snow]){assert.equal(effect.material.stencilFunc,THREE.NotEqualStencilFunc);assert.ok(effect.renderOrder>fx.indoorMask.renderOrder);}
 fx.set({kind:'clear'},true);assert.equal(fx.indoorMask.visible,false);
});
