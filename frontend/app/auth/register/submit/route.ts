import {NextRequest,NextResponse} from 'next/server';
export async function POST(request:NextRequest){
  if(process.env.STRIDE_ACCOUNTS_ENABLED!=="true")return NextResponse.json({detail:"Account mode is disabled."},{status:404});
  const origin=request.headers.get('origin');
  const host=request.headers.get('x-forwarded-host')||request.headers.get('host');
  if(origin&&new URL(origin).host!==host)return NextResponse.json({detail:'Invalid origin'},{status:403});
  if(Number(request.headers.get('content-length')||0)>8192)return NextResponse.json({detail:'Request too large'},{status:413});
  const action=request.nextUrl.pathname.split('/').at(-2);
  const upstream=await fetch(`${process.env.BACKEND_URL||'http://127.0.0.1:8000'}/api/auth/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:await request.text()});
  const response=new NextResponse(await upstream.text(),{status:upstream.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  const cookie=upstream.headers.get('set-cookie');if(cookie)response.headers.set('set-cookie',cookie);
  return response;
}
