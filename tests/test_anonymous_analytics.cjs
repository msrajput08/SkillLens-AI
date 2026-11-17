'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../app/static/analytics.js'),'utf8');

function boot({preferences={},gpc=false,dnt=null,url='?utm_source=linkedin&resume=secret',pathname='/'}={}) {
  const memory=new Map(Object.entries(preferences));
  const requests=[];
  const button={listeners:new Map(),addEventListener(t,cb){this.listeners.set(t,cb);},
    setAttribute(){},disabled:false,textContent:''};
  const document={
    readyState:'complete',cookie:'',
    querySelectorAll:selector=>selector==='[data-analytics-optout]'?[button]:[],
  };
  const globals={
    document,
    window:{doNotTrack:null},
    navigator:{globalPrivacyControl:gpc,doNotTrack:dnt},
    location:{pathname,search:url,hostname:'example.org'},
    localStorage:{
      getItem:k=>memory.get(k)??null,
      setItem:(k,v)=>memory.set(k,v),
      removeItem:k=>memory.delete(k),
    },
    URLSearchParams,
    fetch:(url,options)=>{requests.push({url,options});return Promise.resolve({status:204});}
  };
  vm.runInNewContext(src,globals,{filename:'analytics.js'});
  return {requests,globals,memory,button};
}

test('no banner, no third-party analytics and one anonymous page-view request',()=>{
  const {requests,globals}=boot();
  assert.equal(requests.length,1);
  assert.equal(requests[0].url,'/api/analytics/event');
  const item=JSON.parse(requests[0].options.body);
  assert.deepEqual(item,{
    event:'page_view',page:'/',source:'none',feature:'none',channel:'linkedin'
  });
  assert.equal(requests[0].options.credentials,'omit');
  assert.equal(requests[0].options.keepalive,true);
  assert.equal(JSON.stringify(requests).includes('secret'),false);
  assert.equal(typeof globals.window.gtag,'undefined');
});

test('funnel events have strict allowlist, never include user data',()=>{
  const {requests,globals}=boot();
  globals.window.skilllensTrack('analysis_completed',{
    feature:'analysis',source:'account',resume_text:'private', email:'private@example.org'
  });
  globals.window.skilllensTrack('unapproved',{source:'private'});
  assert.equal(requests.length,2);
  const obj=JSON.parse(requests[1].options.body);
  assert.equal(obj.event,'analysis_completed');
  assert.equal(obj.feature,'analysis');
  assert.equal(obj.source,'account');
  assert.deepEqual(Object.keys(obj).sort(),['channel','event','feature','page','source']);
});

test('existing opt-out and Global Privacy Control are honored',()=>{
  for(const opts of [
    {preferences:{'skilllens.analytics.consent.v1':'decline'}},
    {preferences:{'skilllens.analytics.optout.v1':'true'}},
    {gpc:true},
    {dnt:'1'}
  ]){
    const {requests,globals}=boot(opts);
    globals.window.skilllensTrack('analysis_completed');
    assert.equal(requests.length,0,JSON.stringify(opts));
  }
});

test('new opt-out button turns off future anonymous event posts',()=>{
  const {requests,globals,button,memory}=boot();
  button.listeners.get('click')();
  assert.equal(memory.get('skilllens.analytics.optout.v1'),'true');
  globals.window.skilllensTrack('preview_completed');
  assert.equal(requests.length,1);
  button.listeners.get('click')();
  globals.window.skilllensTrack('preview_completed');
  assert.equal(requests.length,2);
});

test('unknown UTM source is grouped as other, no query data is sent',()=>{
  const {requests}=boot({url:'?utm_source=John%40example.com&password=secret',pathname:'/builder'});
  const obj=JSON.parse(requests[0].options.body);
  assert.equal(obj.channel,'other');
  assert.equal(obj.page,'/builder');
  assert.equal(JSON.stringify(obj).includes('John'),false);
});
