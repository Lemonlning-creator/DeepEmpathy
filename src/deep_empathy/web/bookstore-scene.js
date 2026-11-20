import * as THREE from './vendor/three/three.module.js';
import {ExteriorWeather,weatherStyle,applyWeatherLighting} from './bookstore-weather.mjs?v=20261120-weather-mask4';
import {OrbitControls} from './vendor/three/OrbitControls.js';
import {BOOKS,PLACES,SEATS,SOFAS,TABLES,EXHIBITION,turnToward} from './bookstore-state.mjs?v=20261120-indoor-mask6';

export class BookstoreScene {
  constructor(container,world,{onPick,onFloor}){
    this.world=world;this.container=container;this.onPick=onPick;this.onFloor=onFloor;this.pickables=[];this.people={};this.labels=[];this.lastTime=performance.now();this.walkWaiters=new Map();
    this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#e8e5dc');this.scene.fog=new THREE.Fog('#e8e5dc',25,60);
    this.camera=new THREE.PerspectiveCamera(32,1,.1,100);this.camera.position.set(10,11,14);
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,stencil:true});this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFShadowMap;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.15;
    this.renderer.domElement.setAttribute('aria-label','可旋转、缩放并点击家具的三维书店');container.prepend(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.target.set(-1,-.15,.1);this.controls.enableDamping=true;this.controls.minDistance=11;this.controls.maxDistance=27;this.controls.minPolarAngle=.3;this.controls.maxPolarAngle=1.25;this.controls.minAzimuthAngle=-.25;this.controls.maxAzimuthAngle=1.45;this.controls.maxTargetRadius=3;
    this.raycaster=new THREE.Raycaster();this.pointer=new THREE.Vector2();this.materials=new Map();
    this.setupLights();this.buildRoom();this.buildFurniture();this.buildPeople();this.buildProps();this.setupPicking();this.weatherEffect=new ExteriorWeather(this.scene);this.open=true;this.weather={kind:'unknown'};
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(container);this.resize();
    this.frame=this.frame.bind(this);this.animation=requestAnimationFrame(this.frame);
  }
  setOpen(open){
    this.container.classList.toggle('is-closed',!open);
    this.container.dataset.storeState=open?'open':'closed';
    this.container.closest('.world-panel')?.classList.toggle('store-closed',!open);
    for(const label of this.labels){
      if(label.person)continue;
      label.element.disabled=!open&&!(label.id==='door'&&this.world.people.user.present);
      label.element.title=open?'':'书屋已闭店，仍可线上聊天';
      if(label.id==='door')label.element.textContent=open?label.dayText:this.world.people.user.present?'整理离店':'已闭店';
    }
    this.open=open;this.applyEnvironment();
  }
  setWeather(weather){this.weather=weather;this.applyEnvironment();}
  applyEnvironment(){
    const open=this.open!==false,style=weatherStyle(this.weather?.kind);
    this.weatherEffect?.set(this.weather,open);
    applyWeatherLighting(this.ambientLight,this.sunLight,this.weather?.kind,open);
    this.scene.background.set(open?style.sky:(style.rain?'#101d2a':'#131b24'));this.container.closest('.world-panel')?.style.setProperty('background-color',`#${this.scene.background.getHexString()}`);this.scene.fog.color.copy(this.scene.background);this.scene.fog.near=45;this.scene.fog.far=this.weather?.kind==='fog'?90:110;
    this.windowSky?.material.color.set(open?(style.rain?'#839ca8':style.snow?'#ccd9dc':'#b6cbc3'):'#273641');
  }

  material(color,extra={}){const key=String(color)+JSON.stringify(extra);if(!this.materials.has(key))this.materials.set(key,new THREE.MeshStandardMaterial({color,roughness:.8,...extra}));return this.materials.get(key);}
  box(parent,size,pos,color,extra={}){const mesh=new THREE.Mesh(new THREE.BoxGeometry(...size),this.material(color,extra));mesh.position.set(...pos);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  cylinder(parent,top,bottom,height,pos,color){const mesh=new THREE.Mesh(new THREE.CylinderGeometry(top,bottom,height,24),this.material(color));mesh.position.set(...pos);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  sphere(parent,r,pos,color,scale=[1,1,1]){const mesh=new THREE.Mesh(new THREE.SphereGeometry(r,20,16),this.material(color));mesh.position.set(...pos);mesh.scale.set(...scale);mesh.castShadow=true;parent.add(mesh);return mesh;}
  group(pos=[0,0,0]){const g=new THREE.Group();g.position.set(...pos);this.scene.add(g);return g;}
  target(group,target){group.userData.target=target;this.pickables.push(group);return group;}
  textTexture(text,{color='#f5ebd6',background='#3f5949',width=512,height=128,size=42}={}){const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');ctx.fillStyle=background;ctx.fillRect(0,0,width,height);ctx.fillStyle=color;ctx.font=`500 ${size}px "PingFang SC",sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,width/2,height/2,width-30);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;return texture;}
  sign(parent,text,size,pos,options={}){const mesh=new THREE.Mesh(new THREE.PlaneGeometry(...size),new THREE.MeshStandardMaterial({map:this.textTexture(text,options),roughness:1}));mesh.position.set(...pos);parent.add(mesh);return mesh;}
  setupLights(){this.ambientLight=new THREE.HemisphereLight('#fff0d6','#778a7a',2);this.scene.add(this.ambientLight);const sun=new THREE.DirectionalLight('#fff1d7',3.2);sun.position.set(-5,11,8);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);Object.assign(sun.shadow.camera,{left:-10,right:10,top:10,bottom:-10,near:.5,far:35});sun.shadow.bias=-.0005;sun.shadow.normalBias=.025;this.sunLight=sun;this.scene.add(sun);}
  buildRoom(){
    const room=this.group();this.box(room,[14.4,.3,8.5],[-1,-.18,0],'#80644b');
    const floor=this.box(room,[14,.06,8],[-1,-.01,0],'#be9d72');floor.userData.target={type:'floor'};this.pickables.push(floor);
    for(let i=0;i<25;i++){const z=-3.9+i*.32;this.box(room,[13.96,.008,.307],[-1,.025,z],['#c1a17a','#c8aa82','#c5a57c','#caae89'][i%4]);for(let j=0;j<5;j++)this.box(room,[.008,.011,.307],[-7.5+j*3+(i%3)*.4,.029,z],'#b2936a');}
    this.box(room,[14.2,3.4,.16],[-1,1.67,-4.08],'#e9deca');this.box(room,[.18,3.4,4.6],[-8.05,1.67,-1.7],'#e9deca');this.box(room,[.18,.65,3.5],[-8.05,.29,2.25],'#e5d9bf');this.box(room,[.18,2.9,1.8],[6.05,1.42,-3.18],'#e4d5ba');
    this.box(room,[14,.13,.09],[-1,.11,-3.95],'#9f7952');this.box(room,[.08,.13,8],[-7.95,.11,0],'#9f7952');
    // Window, painted sky and timber muntins on the open left wall.
    const window=this.group([-7.94,1.93,.12]);window.rotation.y=Math.PI/2;
    this.windowSky=this.box(window,[2.5,1.8,.08],[0,0,0],'#b6cbc3');this.windowSky.material=this.windowSky.material.clone();for(let k=0;k<5;k++)this.sphere(window,.55,[-1+k*.55,-.6,.06],['#879f89','#91a68c'][k%2],[1,.8,.1]);
    for(const x of [-1.3,0,1.3])this.box(window,[.07,1.96,.16],[x,0,.13],'#f5ebd6');for(const y of [-.96,0,.96])this.box(window,[2.66,.07,.16],[0,y,.13],'#f5ebd6');this.box(window,[2.9,.15,.48],[0,-1.05,.18],'#9b7955');
    // Front threshold and a freestanding timber/glass door, swung open on entry.
    this.box(room,[2.0,.12,1.2],[4.3,-.04,4.22],'#b9a184');
    const door=this.target(this.group([4.3,0,4.0]),{type:'door',id:'door'});this.box(door,[1.85,.13,.18],[0,2.9,0],'#5a6a53');for(const x of [-.9,.9])this.box(door,[.12,2.95,.16],[x,1.45,0],'#5a6a53');
    this.doorPivot=new THREE.Group();this.doorPivot.position.set(-.82,0,0);door.add(this.doorPivot);this.box(this.doorPivot,[1.63,.09,.1],[.815,2.75,0],'#61745e');this.box(this.doorPivot,[1.63,.12,.1],[.815,.15,0],'#61745e');for(const x of [.03,1.6])this.box(this.doorPivot,[.08,2.65,.1],[x,1.45,0],'#61745e');this.box(this.doorPivot,[1.48,2.4,.026],[.815,1.45,0],'#c8d8ce',{transparent:true,opacity:.24,metalness:.05});this.cylinder(this.doorPivot,.025,.025,.28,[1.42,1.3,.1],'#c1a664');
    this.sign(door,'慢屿 · OPEN',[1.13,.31],[0,3.17,.01],{size:40});
    // Low cutaway front wall leaves the door aligned with the counter.
    this.box(room,[11.2,.38,.13],[-2.4,.15,4.05],'#e5d9bf');this.box(room,[.7,.38,.13],[5.65,.15,4.05],'#e5d9bf');
    // Framed sunny artwork behind the counter.
    const frame=this.box(room,[1.36,1.96,.10],[4.65,2.10,-3.94],'#aa7a43');
    const artTexture=new THREE.TextureLoader().load('/static/assets/sunny-bookshop-portrait.png');artTexture.colorSpace=THREE.SRGBColorSpace;
    const art=new THREE.Mesh(new THREE.PlaneGeometry(1.2,1.8),new THREE.MeshStandardMaterial({map:artTexture,roughness:1}));art.position.set(4.65,2.10,-3.88);room.add(art);
    // Front displays.
    const emblem=this.sign(room,'S L O W   I S L A N D',[4.3,.55],[0,3.06,-3.97],{color:'#74694d',background:'#e9deca',size:30});emblem.castShadow=false;
    this.plant([-7.15,0,2.65],1.15);this.plant([5.3,0,3.1],.8);this.plant([5.1,0,-3.0],.95);
  }
  plant(pos,scale=1){const g=this.group(pos);g.scale.setScalar(scale);this.cylinder(g,.26,.18,.45,[0,.22,0],'#b98565');this.cylinder(g,.013,.025,1.0,[0,.8,0],'#6d7550');for(let i=0;i<9;i++){const angle=i*2.4,leaf=this.sphere(g,.3,[Math.sin(angle)*.25,.55+i*.085,Math.cos(angle)*.25],i%2?'#6b8254':'#879665',[.45,.28,1.25]);leaf.rotation.set(.35,angle,.3);}}
  buildFurniture(){
    for(const [index,x] of [-6.87,-4.1,-1,2].entries()){
      const shelf=this.target(this.group([x,0,-3.5]),{type:'shelf',id:`shelf-${['d','a','b','c'][index]}`});
      if(index===0)shelf.scale.x=2/2.65;
      this.box(shelf,[2.65,2.65,.64],[0,1.32,0],'#93714d');this.box(shelf,[2.38,2.46,.035],[0,1.33,.34],'#624d37');
      for(const sx of [-1.3,1.3])this.box(shelf,[.13,2.75,.8],[sx,1.37,.05],'#ad885d');
      for(let row=0;row<4;row++){const y=.2+row*.63;this.box(shelf,[2.65,.09,.82],[0,y,.09],'#b49165');for(let b=0;b<12;b++){const width=.1+(b%3)*.025,height=.32+((b*13+index*7)%8)*.025;const color=['#7a8a73','#b37451','#d2ba85','#6b8389','#8c6853','#b1a786'][(b+index+row)%6];this.box(shelf,[width,height,.28],[-1.13+b*.2,y+height/2+.055,.3],color);this.box(shelf,[width*.85,.014,.012],[-1.13+b*.2,y+height*.7,.446],'#d2be90');}}
      this.box(shelf,[2.72,.16,.9],[0,2.74,.08],'#a27e53');this.sign(shelf,['旅行 · 生活','散文 · 日常','文学 · 晚风','自然 · 来信'][index],[1.7,.23],[0,2.54,.52],{size:32,background:'#96734f'});
    }
    for(const seat of SOFAS){
      const {id,x,z,rotation,color}=seat,width=1.35;
      const sofa=this.target(this.group([x,0,z]),{type:'sofa',id});sofa.rotation.y=rotation;
      for(const sx of [-width/2+.2,width/2-.2])for(const z of [-.33,.32])this.cylinder(sofa,.055,.045,.3,[sx,.16,z],'#765a3c');
      this.box(sofa,[width,.34,1.04],[0,.43,0],color);this.box(sofa,[width,.63,.22],[0,.9,-.45],color);
      for(const sx of [-width/2+.06,width/2-.06])this.box(sofa,[.18,.48,1.08],[sx,.67,0],color);
      this.box(sofa,[width-.4,.2,.78],[0,.66,.07],'#c2c4a5');
    }
    for(const [id,t] of Object.entries(TABLES)){
      const table=this.target(this.group([t.x,0,t.z]),{type:'table',id});
      this.cylinder(table,t.radius,t.radius,.09,[0,t.height,0],'#b69264');
      this.cylinder(table,.055,.08,t.height-.08,[0,(t.height-.08)/2,0],'#8c6e47');
      this.cylinder(table,t.radius*.62,t.radius*.7,.07,[0,.06,0],'#8c6e47');
    }
    // Low central themed book display; kept out of the seating and table rules.
    const display=this.target(this.group([EXHIBITION.x,0,EXHIBITION.z]),{type:'exhibition',id:'exhibition'});
    // Open lower shelf: upright spines, with three tidy book stacks above.
    for(const y of [.16,.88])this.box(display,[2.4,.1,1.25],[0,y,0],'#b49165');
    this.box(display,[2.2,.62,.045],[0,.52,-.55],'#98754e');
    for(const x of [-1.12,0,1.12])this.box(display,[.08,.62,1.1],[x,.52,0],'#a68256');
    const colors=['#81917a','#bf906b','#d2bb8b','#6f8789','#a29273'];
    for(let i=0;i<15;i++){
      const x=-.99+i*.14,h=.37+(i%4)*.035;
      this.box(display,[.105,h,.5],[x,.21+h/2,.23],colors[i%5]);
      this.box(display,[.075,.012,.008],[x,.3+h*.65,.485],'#eee2c3');
    }
    for(let i=0;i<3;i++)for(let j=0;j<3+i%2;j++){
      const x=-.38+i*.53,y=.958+j*.075,z=.12+(i%2)*.06;
      this.box(display,[.43,.065,.58],[x,y,z],colors[(i+j)%5]);
      this.box(display,[.39,.035,.008],[x,y,z+.295],'#e7dec7');
    }
    this.sign(display,'本周主题 · 在故事里慢下来',[1.65,.16],[0,.16,.635],{size:25,background:'#98754e'});
    this.cylinder(display,.14,.11,.25,[-.85,1.055,-.22],'#e2d9c4');
    for(let i=0;i<5;i++){
      const angle=i*2.4;
      this.cylinder(display,.009,.009,.35,[-.85,1.3,-.22],'#748365');
      const leaf=this.sphere(display,.18,[-.85+Math.sin(angle)*.12,1.3+i*.035,-.22+Math.cos(angle)*.12],i%2?'#819879':'#617e65',[.55,1,.35]);leaf.rotation.z=Math.sin(angle)*.65;
    }
    const counter=this.target(this.group([4.3,0,-.25]),{type:'counter',id:'counter'});this.box(counter,[2.5,.96,1.25],[0,.5,0],'#7e8b6e');for(let i=0;i<16;i++)this.box(counter,[.026,.82,.025],[-1.17+i*.155,.53,.64],'#67775a');this.box(counter,[2.65,.12,1.38],[0,1.05,0],'#dbcbb0');this.sign(counter,'慢屿书屋',[1.35,.28],[0,.63,.662],{size:40,background:'#7e8b6e'});
    const register=this.group([3.45,1.13,-.35]);this.box(register,[.4,.05,.32],[0,.03,0],'#4b5548');const screen=this.box(register,[.4,.29,.045],[0,.2,0],'#4b5548');screen.rotation.x=-.2;this.sign(register,'欢迎光临',[.33,.18],[0,.2,.038],{size:55,color:'#e4dfc4',background:'#6f7e6d'});
  }
  buildPeople(){
    for(const [id,coat] of [['boss','#516b56'],['user','#b98163']]){
      const g=this.group(),body=new THREE.Group();g.add(body);const skin='#e1b28e';
      this.box(body,[.42,.48,.24],[0,1.06,0],id==='boss'?'#e5d8bd':coat);this.box(body,[.34,.43,.035],[0,1.02,.14],coat);this.box(body,[.21,.035,.04],[0,.91,.17],id==='boss'?'#a5b18e':coat);
      this.cylinder(body,.095,.095,.12,[0,1.35,0],skin);this.sphere(body,.205,[0,1.55,0],skin,[.93,1.05,.9]);this.sphere(body,.21,[0,1.65,-.025],'#4c4134',[1,.72,1]);
      for(const x of [-.068,.068])this.sphere(body,.016,[x,1.56,.167],'#463e32',[1,1.15,.6]);
      const limbs=[];for(const side of [-1,1]){const leg=new THREE.Group();leg.position.set(side*.115,.77,0);body.add(leg);this.cylinder(leg,.085,.075,.34,[0,-.17,0],id==='boss'?'#6b6854':'#687980');const lower=new THREE.Group();lower.position.y=-.34;leg.add(lower);this.cylinder(lower,.07,.065,.33,[0,-.165,0],id==='boss'?'#6b6854':'#687980');this.box(lower,[.16,.095,.25],[0,-.34,.04],'#655442');
        const arm=new THREE.Group();arm.position.set(side*.27,1.27,0);body.add(arm);this.cylinder(arm,.069,.06,.29,[0,-.145,0],id==='boss'?'#e5d8bd':coat);this.cylinder(arm,.055,.05,.24,[0,-.4,0],skin);this.sphere(arm,.06,[0,-.54,0],skin);limbs.push({leg,lower,arm,side});}
      const holding=new THREE.Group();holding.position.set(0,1.02,.39);body.add(holding);
      const heldBook=new THREE.Group();this.box(heldBook,[.34,.04,.26],[0,0,0],'#bf9362');this.box(heldBook,[.31,.03,.23],[0,.035,0],'#eee3c8');this.box(heldBook,[.006,.04,.23],[0,.055,0],'#ad946a');heldBook.rotation.x=-.35;holding.add(heldBook);heldBook.visible=false;
      this.people[id]={group:g,body,limbs,holding,heldBook};this.label(id,id==='boss'?'林予 · 书店老板':'朋友 · 你',null,true);
    }
  }
  buildProps(){
    this.bookMeshes={};for(const book of BOOKS){const place=PLACES[book.shelf];const g=this.target(this.group([place.point[0]+.82,1.62,-3.0]),{type:'book',id:book.id});this.box(g,[.35,.48,.1],[0,0,0],book.color);this.sign(g,book.title,[.3,.39],[0,0,.057],{width:256,height:384,size:24,background:'#d9c8a2',color:'#625338'});this.bookMeshes[book.id]=g;}
    const machine=this.target(this.group([4.65,1.12,-.25]),{type:'coffee',id:'coffee'});this.box(machine,[.72,.68,.64],[0,.34,0],'#d6cfbe',{metalness:.25,roughness:.45});this.box(machine,[.56,.32,.06],[0,.32,.34],'#3b473e');this.box(machine,[.61,.08,.7],[0,.03,.04],'#65705e');this.cylinder(machine,.03,.03,.16,[-.2,.38,.39],'#baae95');this.cylinder(machine,.08,.08,.13,[.13,.73,-.1],'#645b48');this.lamp=this.sphere(machine,.032,[.18,.55,.337],'#b4cb94');
    const cup=this.target(this.group(),{type:'cup',id:'cup'});this.cylinder(cup,.095,.075,.19,[0,.1,0],'#eee4ce');this.cylinder(cup,.081,.081,.005,[0,.198,0],'#79533a');this.coffeeSurface=cup.children[1];const handle=new THREE.Mesh(new THREE.TorusGeometry(.065,.018,8,20),this.material('#eee4ce'));handle.position.set(.1,.11,0);cup.add(handle);this.cupMesh=cup;
    this.steam=[];for(let i=0;i<4;i++){const particle=new THREE.Mesh(new THREE.SphereGeometry(.03,8,8),new THREE.MeshBasicMaterial({color:'#fff6e9',transparent:true,opacity:.3,depthWrite:false}));cup.add(particle);this.steam.push(particle);}
    this.label('shelves','选一本书',[-1,3.15,-3.5]);this.label('sofa','窗边坐坐',[-6.6,1.9,-.3]);this.label('exhibition','主题书展',[-.6,2.2,.4]);this.label('coffee','一杯咖啡',[4.65,2.2,-.25]);this.label('door','推门进来',[4.3,3.5,4]);
  }
  label(id,text,position,person=false){const element=document.createElement(person?'div':'button');element.className=person?`person-tag ${id}`:'world-label';element.textContent=text;this.container.append(element);if(!person){element.type='button';element.addEventListener('click',()=>this.onPick({type:id==='shelves'?'shelf':id,id:id==='shelves'?'shelf-b':id}));}this.labels.push({id,element,position,person,dayText:text});}
  setupPicking(){const canvas=this.renderer.domElement;this.pointerDown=null;canvas.addEventListener('pointerdown',e=>{this.pointerDown=[e.clientX,e.clientY];});canvas.addEventListener('pointerup',e=>{if(!this.pointerDown||Math.hypot(e.clientX-this.pointerDown[0],e.clientY-this.pointerDown[1])>6)return;const rect=canvas.getBoundingClientRect();this.pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);this.raycaster.setFromCamera(this.pointer,this.camera);const hits=this.raycaster.intersectObjects(this.pickables,true);if(!hits.length)return;let object=hits[0].object;while(object&&!object.userData.target)object=object.parent;if(!object)return;const target=object.userData.target;if(target.type==='floor')this.onFloor([hits[0].point.x,hits[0].point.z]);else this.onPick(target);});}
  resize(){const {width,height}=this.container.getBoundingClientRect();this.camera.aspect=width/Math.max(height,1);this.camera.updateProjectionMatrix();this.renderer.setSize(width,height);}
  resetCamera(){this.camera.position.set(10,11,14);this.controls.target.set(-1,-.15,.1);this.controls.update();}
  waitWalk(id){return new Promise(resolve=>this.walkWaiters.set(id,resolve));}
  frame(time){const dt=Math.min((time-this.lastTime)/1000,30);this.lastTime=time;this.world.tick(dt);this.controls.update();const t=time/1000;this.weatherEffect?.tick(Math.min(dt,.05),t);
    for(const [id,model] of Object.entries(this.people)){const p=this.world.people[id];const appearing=p.present&&!model.wasPresent;model.wasPresent=p.present;model.group.visible=p.present;if(!p.present){if(this.walkWaiters.has(id)){this.walkWaiters.get(id)();this.walkWaiters.delete(id);}continue;}model.group.position.set(p.position[0],0,p.position[1]);model.group.rotation.y=appearing?p.rotation:turnToward(model.group.rotation.y,p.rotation,Math.min(dt,.1));const seated=p.pose==='sitting';const seatOffset=seated?(SEATS[p.seat].height+.085-.77):0;model.body.position.y=THREE.MathUtils.damp(model.body.position.y,seatOffset,12,Math.min(dt,.1));const walking=p.pose==='walking';for(const limb of model.limbs){limb.leg.rotation.x=p.pose==='sitting'?-Math.PI/2:walking?Math.sin(t*9)*.5*limb.side:0;limb.lower.rotation.x=p.pose==='sitting'?Math.PI/2:0;limb.arm.rotation.x=p.gestureRemaining>0?-1.3:p.held?-.55:walking?-Math.sin(t*9)*.4*limb.side:.025*Math.sin(t*1.5);}
      model.holding.position.set(0,p.gestureRemaining>0?1.38:1.02,p.gestureRemaining>0?.22:.39);model.heldBook.visible=p.held?.kind==='book';if(!walking&&this.walkWaiters.has(id)){this.walkWaiters.get(id)();this.walkWaiters.delete(id);}}
    for(const [id,g] of Object.entries(this.bookMeshes)){
      const b=this.world.books[id];g.visible=!b.holder;
      if(b.location.startsWith('table')){const table=TABLES[b.location],stack=Object.values(this.world.books).filter(book=>book.location===b.location),i=stack.findIndex(book=>book.id===id);g.position.set(table.x-.08,table.height+.1+i*.095,table.z-.03);g.rotation.x=-Math.PI/2;g.scale.setScalar(table.radius<.4?.82:1);}
      else{const place=PLACES[b.shelf];g.position.set(place.point[0]+.82,1.62,-3);g.rotation.x=0;g.scale.setScalar(1);}
    }
    const holder=this.world.cup.holder;if(holder){const model=this.people[holder];if(this.cupMesh.parent!==model.holding)model.holding.add(this.cupMesh);this.cupMesh.position.set(.16,.03,0);this.cupMesh.rotation.set(0,0,0);}else{if(this.cupMesh.parent!==this.scene)this.scene.add(this.cupMesh);const table=TABLES[this.world.cup.location];this.cupMesh.position.set(...(table?[table.x+(table.radius<.4?.2:.28),table.height+.05,table.z+.09]:[4.45,1.12,.15]));}
    this.coffeeSurface.visible=this.world.cup.full;for(let i=0;i<this.steam.length;i++){const steam=this.steam[i];steam.visible=this.world.cup.full||this.world.coffee.phase==='brewing';const phase=(t*.35+i*.25)%1;steam.position.set(Math.sin(t*2+i)*.025,.25+phase*.45,Math.cos(t+i)*.025);steam.material.opacity=(1-phase)*.25;steam.scale.setScalar(.6+phase);}
    this.lamp.material.color.set(this.world.coffee.phase==='brewing'?'#d49f48':this.world.coffee.phase==='ready'?'#95b66c':'#aab59a');
    this.doorPivot.rotation.y=THREE.MathUtils.damp(this.doorPivot.rotation.y,this.world.people.user.present?-1.25:0,4,dt);
    for(const label of this.labels){let position=label.position;if(label.person){const p=this.world.people[label.id];label.element.hidden=!p.present;position=[p.position[0],p.pose==='sitting'?1.8:2.05,p.position[1]];}const v=new THREE.Vector3(...position).project(this.camera);label.element.style.transform=`translate(-50%,-50%) translate(${(v.x*.5+.5)*this.container.clientWidth}px,${(-v.y*.5+.5)*this.container.clientHeight}px)`;label.element.style.visibility=v.z>1?'hidden':'visible';}
    this.renderer.render(this.scene,this.camera);this.animation=requestAnimationFrame(this.frame);
  }
  dispose(){cancelAnimationFrame(this.animation);this.resizeObserver.disconnect();this.controls.dispose();this.scene.traverse(obj=>{obj.geometry?.dispose();if(obj.material){for(const m of Array.isArray(obj.material)?obj.material:[obj.material]){m.map?.dispose();m.dispose();}}});this.renderer.dispose();}
}
