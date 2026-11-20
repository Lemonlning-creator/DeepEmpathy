import * as THREE from './vendor/three/three.module.js';

export function exteriorPoint(random=Math.random){
  const side=random();
  if(side<.6)return [(random()-.5)*17,4.5+random()*3.2];
  return [(side<.8?-(8.5+random()*2.2):6.5+random()*2.2),-4.8+random()*9];
}
export function weatherStyle(kind){
  return ({rain:{sky:'#dfe7e9',light:.65,rain:true},storm:{sky:'#cbd7de',light:.48,rain:true},snow:{sky:'#edf0ed',light:.8,snow:true},fog:{sky:'#e6eae5',light:.7},overcast:{sky:'#e9e8df',light:.75},cloudy:{sky:'#eae9df',light:.9}})[kind]||{sky:'#e8e5dc',light:1};
}
// Split directional sun from diffuse sky light: scaling both together preserves hard shadows.
export function applyWeatherLighting(ambient,sun,kind,open=true){
  const profiles={
    clear:{ambient:2,sun:3.2,shadow:.8,radius:1.5,color:'#fff1d7'},
    cloudy:{ambient:2.3,sun:1.4,shadow:.35,radius:4,color:'#f3efe2'},
    overcast:{ambient:3.4,sun:.3,shadow:.1,radius:8,color:'#dce6ee'},
    rain:{ambient:3.3,sun:.16,shadow:.06,radius:10,color:'#d5e2ec'},
    storm:{ambient:2.9,sun:.08,shadow:.03,radius:12,color:'#cbdbe7'},
    snow:{ambient:3.5,sun:.4,shadow:.08,radius:9,color:'#e3edf3'},
    fog:{ambient:3.3,sun:.08,shadow:.02,radius:12,color:'#e0e8e7'},
  };
  const p=profiles[kind]||{ambient:2.35,sun:.6,shadow:.16,radius:6,color:'#e5e9e4'};
  ambient.intensity=open?p.ambient:.07;
  ambient.color.set(kind==='clear'?'#fff0d6':'#fff3dd');ambient.groundColor.set(kind==='clear'?'#778a7a':'#b6a38a');
  sun.intensity=open?p.sun:0;sun.color.set(p.color);
  sun.shadow.intensity=open?p.shadow:0;sun.shadow.radius=p.radius;
  sun.castShadow=open&&p.shadow>0;
}
export class ExteriorWeather{
  constructor(scene){
    this.scene=scene;this.kind='unknown';this.group=new THREE.Group();scene.add(this.group);
    this.count=650;this.anchors=Array.from({length:this.count},()=>{const [x,z]=exteriorPoint();return {x,z,y:Math.random()*7.5,speed:6+Math.random()*3};});
    // Stencil the cutaway room silhouette so exterior precipitation cannot
    // project over the open interior, even when the camera rotates.
    const maskMaterial=new THREE.MeshBasicMaterial({colorWrite:false,depthWrite:false,depthTest:false,transparent:true,side:THREE.DoubleSide,stencilWrite:true,stencilRef:1,stencilFunc:THREE.AlwaysStencilFunc,stencilZPass:THREE.ReplaceStencilOp});
    this.indoorMask=new THREE.Mesh(new THREE.BoxGeometry(14.2,3.65,8.2),maskMaterial);
    this.indoorMask.position.set(-1,1.65,0);this.indoorMask.renderOrder=1;this.group.add(this.indoorMask);
    this.rainGeometry=new THREE.BufferGeometry();this.rainGeometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(this.count*6),3));
    this.rain=new THREE.LineSegments(this.rainGeometry,new THREE.LineBasicMaterial({color:'#d0e3ed',transparent:true,opacity:.52,depthWrite:false}));this.rain.frustumCulled=false;this.group.add(this.rain);
    this.snowGeometry=new THREE.BufferGeometry();this.snowGeometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(this.count*3),3));
    this.snow=new THREE.Points(this.snowGeometry,new THREE.PointsMaterial({color:'#f2f6fa',size:.045,transparent:true,opacity:.75,depthWrite:false}));this.snow.frustumCulled=false;this.group.add(this.snow);
    for(const effect of [this.rain,this.snow]){effect.renderOrder=2;Object.assign(effect.material,{stencilWrite:true,stencilRef:1,stencilFunc:THREE.NotEqualStencilFunc,stencilFail:THREE.KeepStencilOp,stencilZFail:THREE.KeepStencilOp,stencilZPass:THREE.KeepStencilOp});}
    this.ground=new THREE.Group();this.group.add(this.ground);
    for(const [size,pos]of [[[19,.035,3.7],[-1,-.3,6.35]],[[2.7,.035,8.5],[-9.6,-.3,0]],[[2.7,.035,8.5],[7.6,-.3,0]]]){const m=new THREE.Mesh(new THREE.BoxGeometry(...size),new THREE.MeshBasicMaterial({color:'#b1bfc3',transparent:true,opacity:.75}));m.position.set(...pos);this.ground.add(m);}
    this.ripples=[];for(let i=0;i<14;i++){const [x,z]=exteriorPoint();const r=new THREE.Mesh(new THREE.RingGeometry(.09,.105,24),new THREE.MeshBasicMaterial({color:'#d5e2e7',transparent:true,opacity:.3,depthWrite:false,side:THREE.DoubleSide}));r.rotation.x=-Math.PI/2;r.position.set(x,-.269,z);r.userData.phase=Math.random();this.ripples.push(r);this.group.add(r);}
    this.set({kind:'unknown'},true);
  }
  set(weather={},open=true){
    this.kind=weather.kind||'unknown';this.wind=Math.min(12,Number(weather.wind_ms)||0);const style=weatherStyle(this.kind);
    this.rain.material.color.set(open?'#718f9f':'#c0d9e8');this.rain.material.opacity=open?.65:.5;this.indoorMask.visible=!!(style.rain||style.snow);this.rain.visible=!!style.rain;this.snow.visible=!!style.snow;this.ground.visible=!!(style.rain||style.snow);for(const r of this.ripples)r.visible=!!style.rain;
    for(const g of this.ground.children)g.material.color.set(style.snow?(open?'#dce4e4':'#414e58'):(open?'#aebcc1':'#283742'));
  }
  tick(dt,time){
    if(!this.rain.visible&&!this.snow.visible)return;
    const snow=this.snow.visible;const positions=(snow?this.snowGeometry:this.rainGeometry).attributes.position;
    for(let i=0;i<this.count;i++){const p=this.anchors[i];p.y-=dt*(snow?.55:p.speed);if(p.y<-.25)p.y=7.5;const sway=snow?Math.sin(time+i)*.08:0;
      if(snow)positions.setXYZ(i,p.x+sway,p.y,p.z);else{const dx=Math.min(.15,this.wind*.012);positions.setXYZ(i*2,p.x,p.y,p.z);positions.setXYZ(i*2+1,p.x+dx,p.y-.25,p.z+.025);}}
    positions.needsUpdate=true;
    for(const r of this.ripples){const phase=(time*.85+r.userData.phase)%1;r.scale.setScalar(.25+phase*2.8);r.material.opacity=(1-phase)*.35;}
  }
}
