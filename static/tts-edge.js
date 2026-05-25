(function(){
  let currentAudio=null;
  let currentUrl=null;
  let currentButton=null;

  function ttsProvider(){
    try{return localStorage.getItem('hermes-tts-provider')||'browser';}
    catch(_){return 'browser';}
  }

  function cleanupButton(){
    if(currentButton) currentButton.dataset.speaking='0';
    currentButton=null;
  }

  function cleanupPlayback(){
    if(currentAudio){
      currentAudio.onended=null;
      currentAudio.onerror=null;
      try{currentAudio.pause();}catch(_){}
      currentAudio=null;
    }
    if(currentUrl){
      try{URL.revokeObjectURL(currentUrl);}catch(_){}
      currentUrl=null;
    }
    cleanupButton();
  }

  function stop(){
    cleanupPlayback();
  }

  function responseContentType(res){
    return String((res.headers&&res.headers.get&&res.headers.get('content-type'))||'').toLowerCase();
  }

  async function responseErrorMessage(res, fallback){
    const message=fallback||res.statusText||'Edge TTS request failed';
    try{
      const type=responseContentType(res);
      if(type.indexOf('application/json')!==-1||type.indexOf('+json')!==-1){
        const body=await res.json();
        return (body&&(body.error||body.message))||message;
      }
      const text=await res.text();
      return text?text.slice(0,180):message;
    }catch(_){
      return message;
    }
  }

  function isAudioContentType(type){
    return /^audio\//.test(type||'');
  }

  function mediaErrorMessage(audio){
    const err=audio&&audio.error;
    if(!err) return 'Browser could not decode the audio response.';
    const names={1:'aborted',2:'network',3:'decode',4:'unsupported source'};
    const label=names[err.code]||'media';
    const detail=err.message?(' '+err.message):'';
    return 'Browser audio error ('+label+', code '+err.code+').'+detail;
  }

  function blobTypeCandidates(blob){
    const seen={};
    const types=[];
    function add(type){
      const key=type==null?'':String(type).toLowerCase();
      if(seen[key]) return;
      seen[key]=true;
      types.push(type);
    }
    add(blob&&blob.type);
    add('audio/mpeg');
    add('audio/mp3');
    add('');
    return types;
  }

  async function blobWithType(blob, type){
    if(type&&blob.type===type) return blob;
    const buffer=await blob.arrayBuffer();
    return type?new Blob([buffer],{type:type}):new Blob([buffer]);
  }

  function waitForPlayable(audio){
    return new Promise(function(resolve,reject){
      let settled=false;
      function done(fn,value){
        if(settled) return;
        settled=true;
        audio.removeEventListener('canplay',onReady);
        audio.removeEventListener('loadedmetadata',onReady);
        audio.removeEventListener('error',onError);
        fn(value);
      }
      function onReady(){done(resolve);}
      function onError(){done(reject,new Error(mediaErrorMessage(audio)));}
      audio.addEventListener('canplay',onReady,{once:true});
      audio.addEventListener('loadedmetadata',onReady,{once:true});
      audio.addEventListener('error',onError,{once:true});
      if(typeof audio.load==='function') audio.load();
    });
  }

  async function playBlob(blob){
    let lastError=null;
    const candidates=blobTypeCandidates(blob);
    for(let i=0;i<candidates.length;i++){
      const candidate=await blobWithType(blob,candidates[i]);
      const url=URL.createObjectURL(candidate);
      const audio=new Audio();
      try{
        audio.src=url;
        currentUrl=url;
        currentAudio=audio;
        await waitForPlayable(currentAudio);
        await currentAudio.play();
        currentAudio.onended=cleanupPlayback;
        currentAudio.onerror=function(){
          const message=mediaErrorMessage(currentAudio);
          cleanupPlayback();
          if(typeof showToast==='function') showToast((t('tts_edge_failed')||'Edge TTS playback failed.')+' '+message,4000,'error');
        };
        return;
      }catch(err){
        lastError=err;
        if(currentAudio===audio) currentAudio=null;
        if(currentUrl===url) currentUrl=null;
        audio.onended=null;
        audio.onerror=null;
        try{audio.pause();}catch(_){}
        try{URL.revokeObjectURL(url);}catch(_){}
      }
    }
    throw lastError||new Error('Browser could not play the Edge TTS audio response.');
  }

  async function fetchAudio(text){
    const rel='api/tts/edge/audio/speech';
    const url=new URL(rel,document.baseURI||location.href);
    const edgeVoice=localStorage.getItem('hermes-tts-edge-voice')||'';
    const payload={
      input:text,
      voice:edgeVoice.trim(),
      rate:localStorage.getItem('hermes-tts-rate')||'1',
      pitch:localStorage.getItem('hermes-tts-pitch')||'1'
    };
    const res=await fetch(url.href,{
      method:'POST',
      credentials:'include',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    const type=responseContentType(res);
    if(!res.ok){
      const message=await responseErrorMessage(res);
      const err=new Error(message);
      err.status=res.status;
      throw err;
    }
    if(!isAudioContentType(type)){
      const message=await responseErrorMessage(res,'Edge TTS returned a non-audio response.');
      const err=new Error(message);
      err.contentType=type;
      throw err;
    }
    const blob=await res.blob();
    if(!blob||!blob.size){
      throw new Error('Edge TTS returned empty audio.');
    }
    return (blob.type&&blob.type.toLowerCase().indexOf('audio/')===0)?blob:new Blob([blob],{type:type||'audio/mpeg'});
  }

  async function speakText(text, btn){
    const clean=String(text||'').trim();
    if(!clean) return;
    stop();
    currentButton=btn||null;
    if(currentButton) currentButton.dataset.speaking='1';
    try{
      const blob=await fetchAudio(clean);
      await playBlob(blob);
    }catch(err){
      stop();
      if(typeof showToast==='function') showToast((err&&err.message)||t('tts_edge_failed'),4000,'error');
    }
  }

  window.HermesEdgeTTS={
    isSelected:function(){return ttsProvider()==='edge';},
    speakText:speakText,
    stop:stop
  };
})();
