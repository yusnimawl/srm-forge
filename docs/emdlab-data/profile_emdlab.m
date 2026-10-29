function profile_emdlab()
% Line-level profile of one emdlab 8/6 solve at ~40k nodes, then the shipped 30-position sweep.
addpath(genpath('C:\emdlab-win64'));
cd('C:\emdlab-win64\examples\switched-reluctance-machine');
s = build(0.5);
profile on;
evalc('s.solve;');
profile off;
p = profile('info');
ft = p.FunctionTable;
names = {ft.FunctionName}; tt = [ft.TotalTime]; [~, ord] = sort(tt, "descend");
for q = ord(1:12), fprintf('  %7.3fs %s\n', tt(q), names{q}); end
k = find(contains({ft.FileName}, "ms2d_tl3_ihnl") & endsWith(names, "solve"), 1);
f = ft(k);
fprintf('Function %s total %.2fs\n', f.FunctionName, f.TotalTime);
[~, o] = sort(f.ExecutedLines(:,3), 'descend');
src = splitlines(fileread(which('emdlab_solvers_ms2d_tl3_ihnl')));
for i = 1:min(12, numel(o))
    r = f.ExecutedLines(o(i),:);
    fprintf('%6.3fs %4dx L%-4d %s\n', r(3), r(2), r(1), strtrim(src{r(1)}));
end
tx = tic;
evalc('run(''emdlab_examples_srm86_static_torque.m'')');
fprintf('30-position static torque sweep (rebuilds geometry+mesh each position): %.1fs\n', toc(tx));
end

function s = build(scale)
gv_Ns = 8; gv_Nr = 6; gv_Dsh = 20; gv_ISD = 74; gv_OSD = 125; gv_gap = 0.5;
f_mesh = @(r) scale*interp1([gv_Dsh/2,gv_ISD/2,gv_OSD/2], [7.53/2,0.4,7.7/2], r, 'linear','extrap');
g = emdlab_g2d_db;
emdlab_g2d_lib_srm1(g, gv_Ns, gv_Nr, gv_Dsh, gv_ISD, gv_OSD, gv_gap, 19.8*pi/180, 17.1*pi/180, 7.53, 7.7);
g.setMeshLengthByRadialFunction(f_mesh);
evalc('m = g.generateMesh(''mg0'');'); m.setPrintFlag(0);
m.addMaterial('m530', emdlab_mlib_es_M530_50A); m.addMaterial('copper', emdlab_mlib_copper);
m.setMaterial('Rotor','m530'); m.setMaterial('Stator','m530'); m.setMaterial('sca','copper');
m.aux_cmxjcrj('Rotor', gv_Nr); m.aux_cmxjcrj('Stator', gv_Ns); m.aux_cmxjcrj('RotorAP', gv_Nr); m.aux_cmxcr('sca', gv_Ns);
m.rotateMeshZone('Rotor', -15*pi/180); m.rotateMeshZone('RotorAP', -15*pi/180);
m.aux_addCircularAirGap('ag',0,0,gv_ISD/2-gv_gap,0,0,gv_ISD/2,3);
s = emdlab_solvers_ms2d_tl3_ihnl(m); s.setLengthUnit('mm'); s.setDepth(70);
s.defineCoil('phaseA');
s.addMeshZone2Coil('phaseA','sca11',278,1); s.addMeshZone2Coil('phaseA','sca21',278,-1);
s.addMeshZone2Coil('phaseA','sca15',278,-1); s.addMeshZone2Coil('phaseA','sca25',278,1);
s.setCoilCurrent('phaseA', 3.6); s.setAzBC(m.getfbn, 0);
end
