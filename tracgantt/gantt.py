# Copyright (c) 2005, 2006 Will Barton
# All rights reserved.
#
# Author: Will Barton <wbb4@opendarwin.org>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#   1. Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#   2. Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#   3. The name of the author may not be used to endorse or promote products
#      derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL
# THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Standard Python modules
import datetime
import os
import re
import sys
import tempfile
import time
import traceback

# Trac
from trac import util
from trac.core import *
#from trac.core import ComponentManager
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor, ITemplateProvider
from trac.perm import IPermissionRequestor, PermissionSystem
from trac.ticket.model import Ticket
from trac import db_default

class GanttComponent(Component):

    implements(INavigationContributor, IRequestHandler,
            ITemplateProvider, IPermissionRequestor)

    # INavigationContributor
    def get_active_navigation_item(self, req):
        return 'gantt'
    def get_navigation_items(self, req):
        yield ('mainnav', 'gantt',
            util.Markup('<a href="%s">Gantt Charts</a>' \
                                       % self.env.href.gantt()))

    # ITemplateProvider
    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        return [('gantt',resource_filename(__name__, 'htdocs'))]
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    # IPermissionRequestor methods
    def get_permission_actions(self):
        actions = ['GANTT_VIEW']
        return actions + [('GANTT_ADMIN', actions)]

    # IRequestHandler methods
    def match_request(self, req):
        match = re.match(r'/gantt(?:/([0-9]+))?', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = match.group(1)
            return 1

    def process_request(self, req):
        # We require both the ability to view reports and the ability to
        # view gantt charts, since gantt charts are from reports.
        req.perm.assert_permission('REPORT_VIEW')
        req.perm.assert_permission('GANTT_VIEW')

        id = int(req.args.get('id', -1))
        action = req.args.get('action', 'list')

        db = self.env.get_db_cnx()

        if id == -1:
            title = 'Available Charts'
            description = 'This is a list of charts available.'

            cols,rows = self._reports(db)

            req.hdf['gantt.id'] = -1
            req.hdf['title'] = title
            req.hdf['description'] = description
            req.hdf['cols'] = cols
            req.hdf['rows'] = rows

            add_stylesheet(req, 'common/css/report.css')
        else:
            add_link(req, 'up', self.env.href.gantt(), 'Available Charts')
            report = self._report_for_id(db, id)

            if report['id'] > 0:
                report['title'] = '{%i} %s' % (report['id'], report['title'])

            req.hdf['title'] = report['title']
            req.hdf['gantt.title'] = report['title']
            req.hdf['gantt.id'] = report['id']

            show_opened = self.env.config.getbool('gantt-charts',
                    'show_opened', 'false')

            tickets,dates,broken = self._tickets_for_report(db, report['query'])
            tickets,dates = self._paginate_tickets(tickets, dates)

            req.hdf['gantt.tickets'] = tickets
            req.hdf['gantt.dates'] = dates
            req.hdf['gantt.broken'] = broken
            req.hdf['gantt.broken_no'] = len(broken)
            req.hdf['gantt.show_opened'] = show_opened

        add_stylesheet(req, 'gantt/gantt.css')
        return 'gantt.cs', None

    def _reports(self, db):
        cursor = db.cursor()
        cursor.execute("SELECT id AS report,title FROM report ORDER BY "
                + "report")
        info = cursor.fetchall() or []
        cols = [s[0] for s in cursor.description or []]
        db.rollback()
        rows = [{'report':i[0], 'title':i[1],
                'href':self.env.href.gantt(i[0])} for i in info]
        return cols, rows

    def _report_for_id(self, db, id):
        cursor = db.cursor()

        # The 'sql' column changed to 'query' in 0.10, so we want to
        # continue supporting both cases.
        # This happened at http://trac.edgewall.org/changeset/3300,
        # apparently the new db_version is 19 (with the query column)
        if db_default.db_version >= 19:
            cursor.execute("SELECT title,query,description from report " \
                    + "WHERE id=%s", (id,))
        else:
            cursor.execute("SELECT title,sql,description from report " \
                    + "WHERE id=%s", (id,))

        row = cursor.fetchone()
        if not row:
            raise util.TracError('Report %d does not exist.' % id,
                'Invalid Report Number')
        title = row[0] or ''
        query = row[1]
        description = row[2] or ''

        return {'id':id, 'title':title, 'query':query, 'description':description}

    def _tickets_for_report(self, db, query):
        """ Get a list of Ticket instances for the tickets in a report """

        tickets = []
        dates = []
        broken = []

        ## Get tickets for this report
        cursor = db.cursor()
        cursor.execute(query)
        info = cursor.fetchall() or []
        cols = [s[0] for s in cursor.description or []]
        db.rollback()

        ## Functions for processing the SQL results into the datatypes
        ## we need

        # Function to check if ticket is included in the gantt chart
        ticket_in_gantt = lambda t : \
                int(t.values.get('include_gantt', 0)) != 0

        # Function to strip everything but numbers out of the given
        # string, and create an int.  Closed ticket ids have a unicode
        # checkmark.
        # XXX: This is ugly, since we can't guarnatee types on ticket
        # ids, we cast to a string, then replace any chars, and then
        # back to int.
        ticket_id = lambda i : int(re.sub("[^0-9]*", "", str(i)))

        # Function to append a Ticket object to a result row
        ticket_for_info = lambda r : Ticket(self.env,
                ticket_id(r[cols.index('ticket')]))

        ## Now process the results

        # Add ticket objects to each row in the query result,
        # Note: fetchall() returns a list of tuples, so we have to
        # convert those tuples to lists
        # XXX: the cols bit sucks.
        tlist = map(ticket_for_info, info)

        # Create a dict from that list with ticket.id as the keys
        tdict = {}
        map(lambda t : tdict.setdefault(t.id, t),
                filter(ticket_in_gantt, tlist))

        show_opened = self.env.config.getbool('gantt-charts',
                'show_opened', 'false')

        for i in range(len(info)):
            row = info[i]

            # If we get a KeyError, the ticket is not in tdict, because
            # it is not checked to include in gantt charts.
            try:
                ticket = tdict[row[cols.index('ticket')]]
            except KeyError:
                continue

            try:
                # Get the due to start, due to end, open, and last
                # change time for the ticket (this also takes into
                # consideration dependencies times.)
                start,end,open,changed = \
                        self._dates_for_ticket(ticket, tdict)

                # Limit the summary to the max characters configured, or
                # 16 chars in the gantt chart display.  We expose the
                # full summary to the template, but it's not currently
                # used.
                try:
                    sumlen = self.env.config.getint('gantt-charts',
                            'summary_length', 16)
                except AttributeError:
                    sumlen = int(self.env.config.get('gantt-charts',
                            'summary_length', 16))

                summary = ticket.values['summary']

                if len(summary) > sumlen:
                    shortsum = "%s..." % summary[:16]
                else:
                    shortsum = summary

                tickets.append(
                        {'id': ticket.id,
                         'summary':summary,
                         'shortsum':shortsum,
                         'href': self.env.href.ticket(ticket.id),
                         'start': start.toordinal(),
                         'end': end.toordinal(),
                         'open': open.toordinal(),
                         'changed': changed.toordinal(),
                         'color': row[cols.index("__color__")]
                         })

                if start not in dates: dates.append(start)
                if end not in dates: dates.append(end)
                if open not in dates and show_opened:
                    dates.append(open)

            except Exception, e:
                self.env.log.debug("Exception for ticket %s" % ticket.id)
                self.env.log.debug(e)
                broken.append(
                        {'id': ticket.id,
                         'href': self.env.href.ticket(ticket.id),
                         'error':str(e)})

        # Get the dates from the tdict, stored as both string values and
        # ordinal values
        # Catching a NameError if we're in python 2.3
        try:
            dates = [{'str':str(d), 'ord':d.toordinal()} \
                    for d in sorted(dates)]
        except NameError:
            dates.sort()
            dates = [{'str':str(d), 'ord':d.toordinal()} for d in dates]

        # Using that dates list, set the spans of each ticket in the
        # tickets list.
        dlist = [d['ord'] for d in dates]
        map(lambda t : \
                t.setdefault('span',
                        1 + dlist.index(t['end']) - dlist.index(t['start'])),
            tickets)
        if show_opened:
            map(lambda t : \
                    t.setdefault('ospan', dlist.index(t['start'])
                                - dlist.index(t['open'])),
                tickets)

        return tickets,dates,broken

    def _dates_for_ticket(self, ticket, tdict):
        import locale

        # XXX: Conf value
        date_format = self.env.config.get('gantt-charts', 'date_format',
                '%m/%d/%Y')

        # Function to create date objects from date strings
        date_for_string = lambda s,f : datetime.date.fromtimestamp(
                time.mktime(time.strptime(s,f)))
        date_from_date_by_num = lambda n,s : \
            datetime.date.fromordinal(s.toordinal() + int(n))

        depends = ticket.values.get('dependencies')

        # Get the start date, if there is one, otherwise we'll find it
        # later through dependencies
        start_s = ticket.values.get('due_assign')
        if start_s:
            start = date_for_string(start_s, date_format)
        else:
            start = None

        # Cycle through the depends values, and set the start date
        # appropriately if necessary, based on the due date of a dep
        if depends:
            for d in depends.split(","):
                d = int(d.strip().strip("#"))

                # If the dependency is not in the ticket dictionary,
                # it's either closed or not included in gantt charts,
                # therefore we ignore it.
                if d not in tdict.keys(): continue

                d_start,d_due,o,c = self._dates_for_ticket(tdict[d], tdict)
                if not start or d_due > start: start = d_due

        # The start date is optional when the ticket depends on another
        # ticket, otherwise if it is None, we've got a problem.
        #
        # Unless explicitly disabled in the config file, use the
        # creation date as the start date for this ticket.
        if not start:
            use_cdate = self.env.config.getbool("gantt-charts",
                    "use_creation_date", "true")

            if use_cdate:
                start = datetime.date.fromtimestamp(ticket.time_created)
            else:
                raise ValueError, "Couldn't get start date"

        due_s = ticket.values.get('due_close')
        if not due_s:
            raise ValueError, "due date required for inclusion"

        # due_close can either be an integer for number of days from
        # the start, or an actual date matching our format.  Try the
        # date first, then if we get a value error (it doesn't match
        # the format), try it as an integer
        try:
            due = date_for_string(due_s, date_format)
        except ValueError, e:
            due = date_from_date_by_num(due_s, start)

        # If the start date is greater than the due date, something
        # is wrong, so we raise an error, which will mark this
        # ticket as broken for gantt purposes
        if start > due:
            raise ValueError, \
                    "Ticket #%s start date (%s) is after due date (%s)" \
                    % (str(ticket.id), str(start), str(due))

        # Finally the ticket itself's open and close dates
        open = datetime.date.fromtimestamp(ticket.time_created)
        changed = datetime.date.fromtimestamp(ticket.time_changed)

        return (start, due, open, changed)

    def _paginate_tickets(self, tickets, dates):
        return tickets, dates

