import os
import sys
import traceback
from copy import deepcopy
from datetime import datetime

import cfg
import discord
import functions as func
import psutil
import pytz
import utils
from functions import echo, log

try:
    import patreon_info
except ImportError:
    patreon_info = None


async def admin_command(cmd, ctx):
    client = ctx['client']
    message = ctx['message']
    channel = message.channel
    params = ctx['params']
    params_str = ctx['params_str']
    guilds = ctx['guilds']
    LAST_COMMIT = ctx['LAST_COMMIT']

    if cmd == 'log':
        logfile = "log{}.txt".format("" if cfg.SAPPHIRE_ID is None else cfg.SAPPHIRE_ID)
        if not os.path.exists(logfile):
            await channel.send("No log file")
            return
        with open(logfile, 'r', encoding="utf8") as f:
            data = f.read()
        data = data[-10000:]  # Drop everything but the last 10k characters to make string ops quicker
        data = data.replace('  Creating channel for ', '  ✅')
        data = data.replace('  Deleting ', '    ❌')
        data = data.replace('  Renaming ⌛  to  ', ' ⏩ ')
        data = data.replace('  Renaming ', ' 🔄')
        data = data.replace('  to  ', ' ⏩ ')
        data = data.replace('  CMD Y: ', '  C✔ ')
        data = data.replace('  CMD F: ', '  C✖ ')
        data = data.replace(" creating channels too quickly", " creating channels too quickly❗❗")
        data = data.replace(" where I don't have permissions", " where I don't have permissions❗❗")
        data = data.replace("Traceback (most recent", "❗❗Traceback (most recent")
        data = data.replace("discord.errors.", "❗❗discord.errors.")
        data = data.replace("Remembering channel ", "❗❗Remembering ")
        data = data.replace("New tickrate is ", "🕐")
        data = data.replace(", seed interval is ", " 🕐")
        data = data.replace('  ', ' ')  # Reduce indent to save character space
        today = datetime.now(pytz.timezone(cfg.CONFIG['log_timezone'])).strftime("%Y-%m-%d")
        data = data.replace(today, 'T')
        character_limit = 2000 - 17  # 17 for length of ```autohotkey\n at start and ``` at end.
        data = data[character_limit * -1:]
        data = data.split('\n', 1)[1]
        lines = data.split('\n')
        for i, l in enumerate(lines):
            # Fake colon (U+02D0) to prevent highlighting the line
            if " ⏩" in l:
                lines[i] = l.replace(':', 'ː')
            elif l.startswith('T '):
                if '[' in l:
                    s = l.split('[', 1)
                    lines[i] = s[0] + '[' + s[1].replace(':', 'ː')
        data = '\n'.join(lines)
        data = '```autohotkey\n' + data
        data = data + '```'
        await channel.send(data)

    if cmd == 'stats':
        r = await channel.send(". . .")
        t1 = message.created_at
        t2 = r.created_at
        response_time = (t2 - t1).total_seconds()
        num_users = 0
        for g in guilds:
            num_users += len([m for m in g.members if not m.bot])

        lines_of_code = 0
        for f in os.listdir(cfg.SCRIPT_DIR):
            if f.lower().endswith('.py'):
                lines_of_code += utils.count_lines(os.path.join(cfg.SCRIPT_DIR, f))
            elif f == "commands":
                for sf in os.listdir(os.path.join(cfg.SCRIPT_DIR, f)):
                    if sf.lower().endswith('.py'):
                        lines_of_code += utils.count_lines(os.path.join(cfg.SCRIPT_DIR, f, sf))

        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        await r.edit(content=(
            "Servers: **{tot_servs}** (A:{active_servs} S:{shards}) \t "
            "Users: **{users}** \t Channels: **{channels}** \n"
            "Response time: **{rt}** \t Tick rate: **{tr}** \t Tick time: **{tt}** | **{gtt}**\n"
            "CPU: **{cpu}%** \t MEM: **{memg} ({memp}%)** \t DISK: **{diskg} ({diskp}%)**\n"
            "**Last commit:** {commit}\n"
            "**Lines of code:** {lines}\n"
            "**Timings:** {timings}".format(
                tot_servs=len(guilds),
                active_servs=utils.num_active_guilds(guilds),
                shards=utils.num_shards(guilds),
                users=num_users,
                channels=utils.num_active_channels(guilds),
                rt="{0:.2f}s".format(response_time),
                tr="{0:.1f}s".format(cfg.TICK_RATE),
                tt="{0:.2f}s".format(cfg.TICK_TIME),
                gtt="{0:.2f}s".format(cfg.G_TICK_TIME),
                cpu=cpu, memg="{0:.1f}GB".format(mem.used / 1024 / 1024 / 1024), memp=round(mem.percent),
                diskg="{0:.1f}GB".format(disk.used / 1024 / 1024 / 1024), diskp=round(disk.percent),
                commit=LAST_COMMIT,
                lines=lines_of_code,
                timings=cfg.TIMING_LOG
            )
        ))

    if cmd == 'top':
        top_guilds = []
        for g in guilds:
            s = func.get_secondaries(g)
            if s:
                top_guilds.append({"name": g.name,
                                   "size": len([m for m in g.members if not m.bot]),
                                   "num": len(s)})
        top_guilds = sorted(top_guilds, key=lambda x: x['num'], reverse=True)[:10]
        r = "**Top Guilds:**"
        for g in top_guilds:
            r += "\n`{}` {}: \t**{}**".format(
                g['size'],
                func.esc_md(g['name']),
                g['num']
            )
        r += "\n\n**{}**".format(utils.num_active_channels(guilds))
        await channel.send(r)

    if cmd == 'patrons':
        if patreon_info is None:
            await channel.send(content='❌')
            return

        patrons = patreon_info.fetch_patrons(force_update=True)
        if not patrons:
            await channel.send(content='❌')
            return
        fields = {}
        auths = patreon_info.update_patron_servers(patrons)
        for p, pv in patrons.items():
            pu = client.get_user(p)
            if pu is not None:
                pn = pu.name
            else:
                pn = "Unknown"
            gn = ""
            if str(p) in auths:
                for s in auths[str(p)]['servers']:
                    gn += "`{}` ".format(s)
                if 'extra_gold' in auths[str(p)]:
                    for s in auths[str(p)]['extra_gold']:
                        gn += "+g`{}` ".format(s)
            fields["`{}` **{}** {}".format(p, pn, cfg.TIER_ICONS[pv])] = gn
        try:
            for field_chunk in utils.dict_chunks(fields, 25):
                e = discord.Embed(color=discord.Color.from_rgb(205, 220, 57))
                e.title = "{} Patrons".format(len(field_chunk))
                for f, fv in field_chunk.items():
                    fv = fv if fv else "None"
                    e.add_field(name=f, value=fv)
                await channel.send(embed=e)
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')

    if cmd == 'status':
        g = utils.strip_quotes(params_str)
        if not g:
            await func.react(message, '❌')
            return
        try:
            await client.change_presence(
                activity=discord.Activity(name=g, type=discord.ActivityType.watching)
            )
            await func.react(message, '✅')
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')

    if cmd == 'settings':
        g = utils.strip_quotes(params_str)
        try:
            int(g)
        except ValueError:
            for x in guilds:
                if x.name == g:
                    g = str(x.id)
                    break
        fname = g + '.json'
        fp = os.path.join(cfg.SCRIPT_DIR, "guilds", fname)
        if os.path.exists(fp):
            g = int(g)
            gn = client.get_guild(g).name
            head = "**{}** `{}`".format(gn, g)
            head += "💎" if func.is_sapphire(g) else ("💳" if func.is_gold(g) else "")
            s = head
            s += "\n```json\n"
            with open(fp, 'r') as f:
                file_content = f.read()
            s += file_content
            s += '```'
            try:
                await channel.send(s)
            except discord.errors.HTTPException:
                # Usually because message is over character limit
                haste_url = await utils.hastebin(file_content)
                await channel.send("{}\n{}".format(head, haste_url))
        else:
            await func.react(message, '❌')

    if cmd == 'disable':
        try:
            g = client.get_guild(int(utils.strip_quotes(params_str)))
            settings = utils.get_serv_settings(g)
            settings['enabled'] = False
            utils.set_serv_settings(g, settings)
            log("Force Disabling", g)
            await func.react(message, '✅')
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')

    if cmd == 'enable':
        try:
            g = client.get_guild(int(utils.strip_quotes(params_str)))
            settings = utils.get_serv_settings(g)
            settings['enabled'] = True
            utils.set_serv_settings(g, settings)
            log("Force Enabling", g)
            await func.react(message, '✅')
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')

    if cmd == 'info':
        cid = utils.strip_quotes(params_str)
        try:
            c = client.get_channel(int(cid))
            members = [m.display_name + " \t {}".format(utils.debug_unicode(m.display_name)) for m in c.members]
            games = []
            for m in c.members:
                if m.activity:
                    games.append(m.activity.name + " \t {}".format(utils.debug_unicode(m.activity.name)))
            s = "**__Server:__** {} `{}`\n**__Name:__** {}\n{}\n\n".format(
                c.guild.name, c.guild.id, c.name, utils.debug_unicode(c.name)
            )
            if c.id in cfg.ATTEMPTED_CHANNEL_NAMES:
                s += "**__Attempted Name:__** {}\n{}\n\n".format(
                    cfg.ATTEMPTED_CHANNEL_NAMES[c.id],
                    utils.debug_unicode(cfg.ATTEMPTED_CHANNEL_NAMES[c.id])
                )
            s += "**__{} Members:__**\n".format(len(members))
            s += '\n'.join(members)
            s += '\n\n**__{} Games:__**\n'.format(len(games))
            s += '\n'.join(games)
            s = s.replace('\n\n\n', '\n\n')
            await channel.send(s)
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')

    if cmd == 'whois':
        uid = utils.strip_quotes(params_str)
        try:
            u = client.get_user(int(uid))
            in_guilds = {}
            for g in client.guilds:
                if u in g.members:
                    m = g.get_member(int(uid))
                    in_guilds[g.id] = {
                        "guild_name": func.esc_md(g.name),
                        "guild_size": g.member_count,
                        "patron": "💎" if func.is_sapphire(g) else ("💳" if func.is_gold(g) else ""),
                        "user_name": func.esc_md(m.display_name),
                        "role": m.top_role.name,
                    }
            if in_guilds:
                s = "**{}**".format(func.user_hash(u))
                s += " \t :b: :regional_indicator_o: :regional_indicator_t:" if u.bot else ""
                can_dm = True
                try:
                    await u.create_dm()
                    can_dm = client.user.permissions_in(u.dm_channel).send_messages
                except discord.errors.Forbidden:
                    can_dm = False
                s += " \t Can DM: {}".format('✅' if can_dm else '❌')

                for gid, g in in_guilds.items():
                    s += "\n{}`{}` **{}** (`{}`) \t {} ({})".format(
                        g['patron'], gid, g['guild_name'], g['guild_size'], g['user_name'], g['role']
                    )

                await echo(s, channel)
            else:
                await channel.send("¯\\_(ツ)_/¯")
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')

    if cmd == 'addsapphire':
        if cfg.SAPPHIRE_ID is not None:
            await channel.send("You need to DM the main public bot for this.")
            await func.react(message, '❌')
            return
        params = params_str.split('\n')
        sapphire = {}
        try:
            for l in params:
                if l.startswith('server:'):
                    l = l.split(':', 1)[1]
                    sapphire['servers'] = [int(l.strip())]
                elif l.startswith('initiator:'):
                    l = l.split(':', 1)[1]
                    sapphire['initiator'] = int(l.strip())
                elif l.startswith('client_id:'):
                    l = l.split(':', 1)[1]
                    sapphire['client_id'] = int(l.strip())
                elif l.startswith('token:'):
                    l = l.split(':', 1)[1]
                    sapphire['token'] = l.strip()
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')
            return
        required_params = ['servers', 'client_id', 'token', 'initiator']
        for p in required_params:
            if p not in sapphire:
                await channel.send(
                    "Missing required parameter: `{}`\n\nExpected syntax:\n```\n"
                    "addsapphire\n"
                    "server: 332246283601313794\n"
                    "initiator: 291185187105275904\n"
                    "client_id: 615868995668672532\n"
                    "token: XXXXXXXXXXXXXXXXXXXXXXXX.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX\n"
                    "```".format(p))
                await func.react(message, '❌')
                return
        new_sapphire_id = str(len(cfg.CONFIG['sapphires']) - 1)
        new_config = deepcopy(cfg.CONFIG)
        new_config['sapphires'][new_sapphire_id] = sapphire
        cfg.CONFIG = utils.get_config()
        utils.write_json(os.path.join(cfg.SCRIPT_DIR, 'config.json'), new_config, indent=4)
        await channel.send("New sapphire added (#{}), now do `reload` here, and for the new bot.\n"
                           "Invite link for the bot is: <{}>".format(
                               new_sapphire_id,
                               cfg.INVITE_LINK.replace('@@CID@@', str(sapphire['client_id']))
                           ))
        await func.react(message, '✅')

    if cmd == 'exit':
        attempts = 0
        while attempts < 100:
            attempts += 1
            if not cfg.WRITES_IN_PROGRESS:
                print("Exiting!")
                await client.close()
                sys.exit()
                break
        else:
            print("Failed to close", cfg.WRITES_IN_PROGRESS)
            await func.react(message, '❌')

    if cmd == 'rename':
        try:
            cid = utils.strip_quotes(params[0])
            c = client.get_channel(int(cid))
            new_name = ' '.join(params[1:])
            if not new_name:
                new_name = "⌛"
            await c.edit(name=new_name)
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')
        else:
            await func.react(message, '✅')
            log("{0}  Force Renaming to {1}".format(cid[-4:], new_name), c.guild)

    if cmd == 'forget':
        try:
            cid = int(utils.strip_quotes(params[0]))
            c = client.get_channel(cid)
            settings = utils.get_serv_settings(c.guild)
            for p, pv in settings['auto_channels'].items():
                tmp = settings['auto_channels'][p]['secondaries'].copy()
                for s, sv in pv['secondaries'].items():
                    if s == cid:
                        del settings['auto_channels'][p]['secondaries'][s]
                        break
            utils.set_serv_settings(c.guild, settings)
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')
        else:
            await func.react(message, '✅')

    if cmd == 'delete':
        try:
            cid = int(utils.strip_quotes(params[0]))
            c = client.get_channel(cid)
            await c.delete()
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')
        else:
            await func.react(message, '✅')

    if cmd == 'whisper':
        params_str = utils.strip_quotes(params_str)
        if '\n' not in params_str:
            await func.react(message, '❌')
            return
        uid, msg = params_str.split('\n', 1)
        try:
            u = await client.fetch_user(uid)
        except discord.errors.NotFound:
            await func.react(message, '❌')
            return
        if u.dm_channel is None:
            await u.create_dm()
        try:
            await u.dm_channel.send(msg)
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')
        else:
            await func.react(message, '✅')

    if cmd == 'cleanprimaries':
        try:
            n_primaries = 0
            n_real_primaries = 0
            for g in client.guilds:
                settings = utils.get_serv_settings(g)
                tmp = {}
                n_primaries += len(settings['auto_channels'])
                for p, pv in settings['auto_channels'].items():
                    c = g.get_channel(p)
                    if c:
                        tmp[p] = pv
                n_real_primaries += len(tmp)
                if len(settings['auto_channels']) != len(tmp):
                    settings['auto_channels'] = tmp
                    utils.set_serv_settings(g, settings)
            await channel.send("Cleaned {} of {} primaries".format(n_real_primaries, n_primaries))
        except:
            await channel.send(traceback.format_exc())
            await func.react(message, '❌')
