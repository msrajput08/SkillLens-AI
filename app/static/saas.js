'use strict';
// Auth and billing controls. Never trust tier status from browser storage or checkout callbacks.
let csrfToken = '';
let currentUser = null;
let authMode = 'login';
const el = id => document.getElementById(id);
const dialog = el('accountOverlay');
const message = text => { el('authMessage').textContent = text; };
const escapeText = x => String(x ?? '');
window.openAccount = () => { dialog.hidden = false; el('authEmail').focus(); };
window.apiFetch = async (path, options = {}) => {
  const opts = {...options, credentials: 'same-origin', headers: {...(options.headers || {})}};
  if (opts.method && !['GET','HEAD','OPTIONS'].includes(opts.method.toUpperCase()) && csrfToken) {
    opts.headers['X-CSRF-Token'] = csrfToken;
  }
  const res = await fetch(path, opts);
  if (res.status === 401) { currentUser = null; showAccount(); }
  return res;
};
function showAccount() {
  el('accountButton').textContent = currentUser ? `${currentUser.tier === 'pro' ? '✦ ' : ''}${currentUser.email}` : 'Sign in / Join free';
  el('authArea').hidden = !!currentUser;
  el('memberArea').hidden = !currentUser;
  if (currentUser) {
    el('memberDetails').textContent = `${currentUser.email} · ${currentUser.tier.toUpperCase()} plan${currentUser.billing_status ? ' · Billing: ' + currentUser.billing_status : ''}`;
    const data = currentUser.usage || {};
    el('memberUsage').replaceChildren();
    for (const [key, value] of Object.entries(data)) {
      const line = document.createElement('div');
      line.textContent = `${key === 'analyze' ? 'Job analyses' : 'Resume rewrites'}: ${value.used} of ${value.limit} this month`;
      el('memberUsage').append(line);
    }
    el('cancelPro').hidden = !(currentUser.billing_status && ['active', 'pending', 'authenticated', 'created', 'halted'].includes(currentUser.billing_status));
    el('checkBillingStatus').hidden = !currentUser.billing_status;
  }
}
async function refreshAccount() {
  const res = await fetch('/api/auth/me', {credentials:'same-origin'});
  if (res.ok) { const data = await res.json(); currentUser = data.user; csrfToken = data.csrf; }
  else { currentUser = null; csrfToken = ''; }
  showAccount();
}
function switchAuth(mode) {
  authMode = mode;
  el('signinTab').classList.toggle('active', mode === 'login');
  el('registerTab').classList.toggle('active', mode === 'register');
  el('authSubmit').textContent = mode === 'login' ? 'Sign in ↗' : 'Create free account ↗';
  el('authPassword').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
  message('');
}
el('signinTab').onclick = () => switchAuth('login');
el('registerTab').onclick = () => switchAuth('register');
el('accountButton').onclick = window.openAccount;
el('closeAccount').onclick = () => { dialog.hidden = true; };
dialog.addEventListener('click', e => { if(e.target === dialog) dialog.hidden = true; });
el('authForm').addEventListener('submit', async e => {
  e.preventDefault(); message('Working…');
  try {
    const path = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    const resp = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({email:el('authEmail').value, password:el('authPassword').value})});
    const data = await resp.json();
    if(!resp.ok)throw Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
    if (authMode === 'register') { switchAuth('login'); message(data.message); }
    else { currentUser = data.user; csrfToken = data.csrf; showAccount(); dialog.hidden = true; }
  } catch(err) { message(err.message); }
});
el('forgotPassword').onclick = async () => {
  const email = el('authEmail').value || prompt('Enter your account email:');
  if (!email) return;
  const resp = await fetch('/api/auth/forgot-password', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});
  const data = await resp.json(); message(data.message || data.detail || 'Unable to send reset instructions.');
};
el('logoutButton').onclick = async () => {
  await apiFetch('/api/auth/logout',{method:'POST'}); csrfToken = ''; currentUser = null;
  showAccount(); message('Signed out.');
};
el('deleteAccountButton').onclick = async () => {
  if(!confirm('Permanently delete your account and all saved reports? This cannot be undone.'))return;
  const resp=await apiFetch('/api/account/delete',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password:el('deletePassword').value})});
  const data=await resp.json(); message(data.message || data.detail || 'Request failed.');
  if(resp.ok){currentUser=null;csrfToken='';showAccount();}
};
async function savedReports() {
  const resp=await apiFetch('/api/reports'); const body=await resp.json();
  if(!resp.ok){message(body.detail || 'Cannot load reports');return;}
  const parent=el('savedReports');parent.replaceChildren();
  if(!body.length){parent.textContent='No reports saved yet.';return;}
  for(const report of body){
    const row=document.createElement('div'); row.className='saved-entry';
    const name=document.createElement('button');name.textContent=report.title;name.type='button';
    name.onclick=async()=>{
      const res=await apiFetch('/api/reports/'+encodeURIComponent(report.id));
      if(!res.ok){message('Report expired or unavailable.');return;}
      window.dispatchEvent(new CustomEvent('skilllens:report',{detail:await res.json()}));dialog.hidden=true;
    };
    const del=document.createElement('button');del.type='button';del.textContent='Delete';del.className='danger-small';
    del.onclick=async()=>{if(!confirm('Delete this saved report?'))return;
      const res=await apiFetch('/api/reports/'+encodeURIComponent(report.id),{method:'DELETE'});
      if(res.ok)await savedReports();};
    row.append(name,del);parent.append(row);
  }
}
el('refreshReports').onclick = savedReports;
el('freePlan').onclick = window.openAccount;
function loadScript(url) {
  return new Promise((resolve,reject)=>{
    if(window.Razorpay){resolve();return;}
    const script=document.createElement('script');script.src=url;script.onload=resolve;script.onerror=()=>reject(Error('Razorpay Checkout failed to load.'));
    document.head.appendChild(script);
  });
}
el('upgradeButton').onclick = async () => {
  if(!currentUser){window.openAccount();return;}
  const btn=el('upgradeButton');btn.disabled=true;
  try {
    const res=await apiFetch('/api/billing/checkout',{method:'POST'});
    const data=await res.json();
    if(!res.ok)throw Error(data.detail || 'Billing unavailable');
    await loadScript('https://checkout.razorpay.com/v1/checkout.js');
    const checkout=new Razorpay({key:data.key,subscription_id:data.subscription_id,name:data.name,
      description:'Monthly SkillLens Pro',prefill:{email:data.email},
      handler: async result=>{
         window.openAccount();
         message('Checking subscription authorization with Razorpay…');
         try {
           const confirmed=await apiFetch('/api/billing/confirm',{
             method:'POST',headers:{'Content-Type':'application/json'},
             body:JSON.stringify({
               razorpay_payment_id:result.razorpay_payment_id,
               razorpay_subscription_id:result.razorpay_subscription_id,
               razorpay_signature:result.razorpay_signature
             })
           });
           const state=await confirmed.json();
           if(!confirmed.ok)throw Error(state.detail||'Checkout verification unavailable.');
           await refreshAccount();
           message(state.message||'Authorization received. Refresh billing status for paid access.');
         }catch(error){
           await refreshAccount().catch(()=>{});
           message('Payment confirmation pending: '+error.message+' Use Refresh billing status or contact support.');
         }
       },
      modal:{ondismiss:()=>{message('Checkout closed. No subscription was confirmed.');}}});
    checkout.on('payment.failed', e=>{message('Payment failed: '+(e?.error?.description||'please retry or use another supported method.'));window.openAccount();});
    checkout.open();
  } catch(err){message(err.message);window.openAccount();}
  finally{btn.disabled=false;}
};
el('cancelPro').onclick = async () => {
  if(!confirm('Request your Pro subscription cancellation at the end of this billing cycle?'))return;
  try{
    const res=await apiFetch('/api/billing/cancel',{method:'POST'});
    const data=await res.json();
    if(!res.ok)throw Error(data.detail||'Cancellation request failed.');
    message(data.message||'Cancellation requested.');
  }catch(err){message(err.message);}
};
const checkBilling = el('checkBillingStatus');
if(checkBilling) checkBilling.onclick = async () => {
  checkBilling.disabled=true;
  try{
    const res=await apiFetch('/api/billing/status',{method:'POST'});
    const data=await res.json();
    if(!res.ok)throw Error(data.detail||'Could not check subscription.');
    message(data.message||'Billing status refreshed.');
    await refreshAccount();
  }catch(err){message(err.message);}
  finally{checkBilling.disabled=false;}
};
async function fromLink(){
  const params=new URLSearchParams(location.search);
  const verify=params.get('verify'),reset=params.get('reset');
  if(verify){
    const res=await fetch('/api/auth/verify?token='+encodeURIComponent(verify));const data=await res.json();
    history.replaceState(null,'','/');window.openAccount();message(data.message||data.detail||'Verification failed.');
  } else if(reset) {
    history.replaceState(null,'','/');window.openAccount();
    const pass=prompt('New password (12+ characters including letters and a number):');
    if(!pass)return;
    const res=await fetch('/api/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:reset,new_password:pass})});
    const data=await res.json();message(data.message||data.detail||'Reset failed.');
  }
}
refreshAccount().then(fromLink).catch(()=>showAccount());

fetch('/api/billing/config').then(r=>r.json()).then(b => {
  const card=document.querySelector('.plan-card.pro');
  if(!card) return;
  card.style.display='block';
  if(b.enabled && b.price === '199' && b.recurring){
    el('proPrice').textContent='₹199 / month';
    el('upgradeButton').hidden=false;
  }else{
    el('proPrice').textContent='Coming soon';
    el('upgradeButton').hidden=true;
  }
}).catch(()=>{});

el('resendVerification').onclick=async()=>{
  const email=el('authEmail').value.trim();
  if(!email){message('Enter your email above.');return;}
  const res=await fetch('/api/auth/resend-verification',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});
  const data=await res.json();message(data.message||data.detail||'Unable to resend verification.');
};

/* One-time Razorpay Orders API TEST flow; isolated from recurring Pro subscriptions. */
const testCheckoutSection = el('testCheckoutCard');
const testCheckoutButton = el('testCheckoutButton');
const testCheckoutStatus = el('testCheckoutStatus');
let testOrderAmount = 100;
function checkoutNotice(value) {
  if (testCheckoutStatus) testCheckoutStatus.textContent = value;
}
fetch('/api/standard-checkout/config',{credentials:'same-origin'})
  .then(r=>r.json()).then(info=>{
    if(info.enabled && info.mode === 'test' && !info.grants_pro){
      testOrderAmount=info.amount;
      testCheckoutButton.textContent = 'Run ₹' + (testOrderAmount/100).toFixed(2) + ' test checkout';
      testCheckoutSection.hidden=false;
    }
  }).catch(()=>{});

if(testCheckoutButton) testCheckoutButton.onclick = async () => {
  if(!currentUser) {
    window.openAccount();
    checkoutNotice('Sign in to run a sandbox checkout.');
    return;
  }
  testCheckoutButton.disabled=true;
  checkoutNotice('Creating your secure test order…');
  try {
    const response=await apiFetch('/api/create-order',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({amount:testOrderAmount,currency:'INR'}),
    });
    const order=await response.json();
    if(!response.ok)throw Error(order.detail||'Could not create test order.');
    await loadScript('https://checkout.razorpay.com/v1/checkout.js');
    let complete=false, verifying=false;
    const checkout=new Razorpay({
      key:order.key_id,
      order_id:order.order_id,
      amount:order.amount,
      currency:order.currency,
      name:'SkillLens AI',
      description:'Sandbox test only — no Pro access',
      prefill:{email:order.email},
      theme:{color:'#16865e'},
      handler:async result=>{
        verifying=true;
        checkoutNotice('Payment returned. Verifying with our server…');
        try {
          const checked=await apiFetch('/api/verify-payment',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
              razorpay_payment_id:result.razorpay_payment_id,
              razorpay_order_id:result.razorpay_order_id,
              razorpay_signature:result.razorpay_signature,
            })
          });
          const verified=await checked.json();
          if(!checked.ok)throw Error(verified.detail||'Payment verification failed.');
          if(!verified.verified)throw Error('Payment was not verified.');
          complete=true;
          checkoutNotice('Test payment verified! This did not activate Pro or charge real money.');
        }catch(err){checkoutNotice(err.message||'Could not verify test payment.');}
        finally{verifying=false;}
      },
      modal:{ondismiss:()=>{
        if(!complete && !verifying)checkoutNotice('Checkout closed. No payment confirmed.');
      }},
    });
    checkout.on('payment.failed',result=>{
      const reason=result?.error?.description || 'Payment failed; no upgrade granted.';
      checkoutNotice('Test payment failed: '+reason);
    });
    checkout.open();
  }catch(err){checkoutNotice(err.message||'Checkout is unavailable.');}
  finally{testCheckoutButton.disabled=false;}
};
